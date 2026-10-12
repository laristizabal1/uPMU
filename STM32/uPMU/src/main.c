/* uPMU: firmware de bring-up en NUCLEO-F303K8 + GPS.
 *
 * Flujo en vivo (60 kS/s -> 30 fps a 60 Hz / 25 fps a 50 Hz):
 *   TIM2 (60 kHz) --TRGO--> ADC1 (V, PA0) + ADC2 (I, PA4) dual --> DMA circular (2 mitades de 256 muestras)
 *   DMA ISR (prio 0, minima) --> ISR "DSP" (EXTI0, prio 3): estadistica, CIC y ventana circular (pipeline.c)
 *   bucle principal: estimador (estimator.c) cada reporte + salida por el puerto serie virtual (USART2).
 * La ISR del PPS (TIM2 CH2, PA1) y el DMA tienen prioridad 0; el DSP (~300 us por mitad) es el menos prioritario
 * para no retrasar la captura del PPS ni los USART.
 *
 * Salidas por USART2 (115200):
 *   PMU,<utc>,<f_Hz>,<V_rms>,<V_ang_deg>,<I_rms>,<I_ang_deg>,<bandera>   una por reporte (ver docs/FORMATO_TRAMA.md)
 *   STATE,<ddmmyy>T<hhmmss.ss>,<fix>,<sats>                             una por segundo (GGA del GPS)
 *   ADC,<n>,<muestras>,<delta>,<ovr>,<proc_ovr>,<tx_drop>,<A m/min/max/std>,<B m/min/max/std>   una por segundo
 *   PPS,<n>,<fase>,<k>,<n_dma>                                           por cada pulso en PA1
 *   VEC / CIC / EST / MEM                                                respuesta a un vector de prueba (T4.x)
 *   #...                                                                 diagnosticos
 * Banderas de compilacion de diagnostico: NMEA_ECHO, UBX_DIAG, PPS_SELFTEST (+PPS_SW), PPS_CALIB, EST_PROFILE,
 * VREF_ON_ADC1 / VREF_ON_ADC2. Las ISR solo guardan datos (regla 7); imprimir va por una cola de transmision. */
#include "stm32f3xx_hal.h"
#include "nmea.h"
#include "vecrx.h"
#include "estimator.h"
#include "pipeline.h"
#include <math.h>
#include <stdio.h>

/* Reloj del sistema: por defecto HSI/2 x 15 = 60 MHz (T1.2, la placa sale con SB4 abierto). Con -DUSE_HSE el reloj
 * de 8 MHz del ST-LINK (MCO) entra por PF0 en bypass (requiere cerrar SB4 y abrir SB6, UM1956 Tabla 5) y el PLL
 * da 72 MHz. Todo lo que depende de la frecuencia del timer sale de estas macros. */
/* Frecuencia del timer y ticks por muestra (60 kS/s): 60 MHz / 1000 con HSI, 72 MHz / 1200 con HSE. Son variables
 * porque, si el cristal externo no arranca, el firmware cae al HSI en tiempo de ejecucion (#CLK lo informa). */
static uint32_t clk_timer_hz = 60000000u;
static uint32_t clk_sample_ticks = 1000u;
static const char *clk_src = "HSI";
#define TIMER_HZ clk_timer_hz
#define SAMPLE_TICKS clk_sample_ticks

#define RING_SIZE 512u /* potencia de 2; a 9600 baudios son ~533 ms de margen */
#define TX_SIZE   512u /* cola de salida del puerto virtual */
#define RX2_SIZE  512u /* PC -> Nucleo; a 115200 baud son ~44 ms de margen */
#define HALF      256u /* muestras por mitad del DMA: 4,27 ms a 60 kS/s */
#define BUF_LEN   (2u * HALF)

static UART_HandleTypeDef huart1; /* GPS */
static UART_HandleTypeDef huart2; /* VCP del ST-LINK */
static ADC_HandleTypeDef  hadc1, hadc2;
static DMA_HandleTypeDef  hdma_adc1;
static TIM_HandleTypeDef  htim2;

/* GPS RX */
static volatile uint8_t  ring[RING_SIZE];
static volatile uint32_t ring_head;     /* escribe la ISR */
static volatile uint32_t ring_tail;     /* lee el bucle principal */
static volatile uint32_t ring_overflow; /* bytes perdidos por buffer lleno */
static volatile uint32_t uart_errors;   /* ORE/FE/NE del USART1 */

/* VCP RX (vectores de prueba desde la PC) */
static volatile uint8_t  rx2_ring[RX2_SIZE];
static volatile uint32_t rx2_head;      /* escribe la ISR */
static volatile uint32_t rx2_tail;      /* lee el bucle principal */
static volatile uint32_t rx2_overflow;  /* bytes perdidos por buffer lleno */
static volatile uint32_t rx2_errors;    /* ORE/FE/NE del USART2 */

/* VCP TX */
static volatile uint8_t  tx_ring[TX_SIZE];
static volatile uint32_t tx_head;       /* escribe el bucle principal */
static volatile uint32_t tx_tail;       /* lee la ISR */
static uint32_t          tx_drop;       /* bytes descartados por cola llena */

/* Ventana deslizante (pipeline.c): S exacto = hi (S >> 2, uint16) + lo (2 bits bajos, 4 por byte), N + holgura
 * salidas por canal. El canal V (hi + lo) va en la CCM-RAM (4 KB, solo CPU, sin inicializar: pipe_init limpia
 * `lo`); el canal I en SRAM. Tambien sirven de ventana a los vectores de prueba (T4.x) cuando el modo en vivo
 * esta en pausa. */
#define CCM __attribute__((section(".ccmram")))
static CCM uint16_t win_hi_v[PIPE_LEN_MAX];
static CCM uint8_t  win_lo_v[(PIPE_LEN_MAX + 3u) / 4u];
static uint16_t     win_hi_i[PIPE_LEN_MAX];
static uint8_t      win_lo_i[(PIPE_LEN_MAX + 3u) / 4u];
static pipe_t       pipe;
static volatile uint8_t live_enabled;   /* 0 durante un vector de prueba o un cambio de modo */

/* ADC: cada palabra = ADC1 (bits 0..15, V) | ADC2 (bits 16..31, I), formato del registro comun CDR */
static uint32_t          adc_buf[BUF_LEN];
static volatile uint32_t adc_blocks;    /* mitades completadas por el DMA */
static volatile uint8_t  adc_ready[2];  /* mitad lista para procesar */
static volatile uint32_t adc_proc_ovr;  /* mitad sobrescrita antes de procesarla */
static volatile uint32_t adc_cycles;    /* vueltas completas del buffer circular (TC del DMA) */
static volatile uint32_t adc_half_idx[2]; /* indice (base 0) de la mitad del DMA lista: muestra absoluta = idx * HALF + i */
static volatile uint8_t  pipe_gap;      /* el DSP detecto una mitad perdida: hay que reiniciar la cadena */

/* Estadistica del ADC: la acumula la ISR de DSP; el bucle principal la lee y la reinicia cada segundo. */
static volatile struct {
    uint64_t sum_a, sum_b, sq_a, sq_b;
    uint32_t n, min_a, max_a, min_b, max_b;
} st = { .min_a = 0xFFFF, .min_b = 0xFFFF };

/* T3.1: captura del PPS en TIM2_CH2 (PA1). La ISR guarda; el bucle principal imprime. */
typedef struct {
    uint32_t phase; /* CCR2: ticks de 60 MHz desde el ultimo disparo del ADC (0..999) */
    uint32_t k;     /* disparos de muestreo hasta el pulso (TIM3 por hardware + desbordes), exacto */
    uint32_t n_dma; /* muestras que el DMA ya habia entregado: k - n_dma = 0 o 1 (ver fase) */
} pps_rec_t;
#define PPS_Q 4u
static pps_rec_t         pps_q[PPS_Q];
static volatile uint32_t pps_head, pps_tail, pps_lost;
static volatile uint32_t tim3_ovf;      /* desbordes de TIM3 (cada 65 536 disparos = 1,09 s) */
#define CAL_ITR 1u /* TIM2_TRGO -> ITR1 en TIM3 (RM0316, disparos internos); se confirmo contando 60 000/s */
#ifdef PPS_CALIB
/* Comparacion A (DMA) vs B (contador por hardware), con verdad independiente: TIM6 dispara capturas
 * cada 59 999 ticks exactos, asi que T = k*1000 + fase debe avanzar 59 999 (+-latencia de la ISR de TIM6).
 * Un error de 1 muestra aparece como +-1000. cmp_mis cuenta los pulsos en que k != n_dma. */
static volatile uint32_t cmp_pairs, cmp_a_bad, cmp_b_bad, cmp_mis, cmp_tc;
static volatile int32_t  cmp_maxdev_b, cmp_maxdev_a;
#endif
#define SAFE_LO (SAMPLE_TICKS * 34u / 100u) /* > retardo de entrega del DMA (~271 ticks de 1000, T3.1) con margen */
#define SAFE_HI (SAMPLE_TICKS * 98u / 100u) /* < periodo menos el retardo de lectura */

void SysTick_Handler(void)
{
    HAL_IncTick();
}

#ifdef NMEA_TS
/* T2.4: sello de tiempo del '$' de cada sentencia en la linea de tiempo del muestreo: k = disparos del ADC
 * (TIM3 por hardware + desbordes) y cnt = TIM2->CNT (ticks de 60 MHz dentro del periodo de 1000). Resolucion de
 * ~1 muestra (16,7 us) por no sincronizar la lectura de TIM3 y TIM2; sobra para medir retardos de milisegundos.
 * Cola de 8: la ISR empuja un sello por cada '$' y el bucle principal saca uno por cada '$' que alimenta al parser. */
static volatile uint32_t ts_k[8], ts_c[8], ts_head, ts_tail, ts_lost;
static void ts_push(void)
{
    uint32_t o1, o2, cnt3, cnt2, pend;
    do {
        o1   = tim3_ovf;
        cnt3 = TIM3->CNT;
        pend = TIM3->SR & TIM_SR_UIF;
        cnt2 = TIM2->CNT;
        o2   = tim3_ovf;
    } while (o1 != o2);
    uint32_t nx = (ts_head + 1u) & 7u;
    if (nx == ts_tail) {
        ts_lost++;
        return;
    }
    ts_k[ts_head] = ((o1 + (pend ? 1u : 0u)) << 16) | cnt3;
    ts_c[ts_head] = cnt2;
    ts_head = nx;
}
#endif

void USART1_IRQHandler(void)
{
    uint32_t isr = USART1->ISR;
    if (isr & (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE)) {
        USART1->ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NCF;
        uart_errors++;
    }
    if (isr & USART_ISR_RXNE) {
        uint8_t b = (uint8_t)USART1->RDR; /* leer RDR limpia RXNE */
#ifdef NMEA_TS
        if (b == '$') ts_push();
#endif
        uint32_t next = (ring_head + 1u) & (RING_SIZE - 1u);
        if (next == ring_tail) {
            ring_overflow++;
        } else {
            ring[ring_head] = b;
            ring_head = next;
        }
    }
}

void USART2_IRQHandler(void)
{
    uint32_t isr = USART2->ISR;
    if (isr & (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE)) {
        USART2->ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NCF;
        rx2_errors++;
    }
    if (isr & USART_ISR_RXNE) { /* PC -> Nucleo: vectores de prueba (T4.1) */
        uint8_t b = (uint8_t)USART2->RDR;
        uint32_t next = (rx2_head + 1u) & (RX2_SIZE - 1u);
        if (next == rx2_tail) {
            rx2_overflow++;
        } else {
            rx2_ring[rx2_head] = b;
            rx2_head = next;
        }
    }
    if ((USART2->CR1 & USART_CR1_TXEIE) && (USART2->ISR & USART_ISR_TXE)) {
        if (tx_tail != tx_head) {
            USART2->TDR = tx_ring[tx_tail];
            tx_tail = (tx_tail + 1u) & (TX_SIZE - 1u);
        } else {
            USART2->CR1 &= ~USART_CR1_TXEIE;
        }
    }
}

void DMA1_Channel1_IRQHandler(void)
{
    HAL_DMA_IRQHandler(&hdma_adc1);
}

/* ISR de DSP (EXTI0 usada como interrupcion por software, prioridad 3 = la menor): procesa las mitades del DMA
 * ya completas. Por muestra: estadistica del ADC y, en modo vivo, CIC + ventana (pipe_push). ~300 us por mitad
 * cada 4,27 ms. La pide la ISR del DMA con NVIC_SetPendingIRQ. */
#define DSP_IRQn EXTI0_IRQn
void EXTI0_IRQHandler(void)
{
    for (unsigned h = 0; h < 2; h++) {
        if (!adc_ready[h]) continue;
        const uint32_t *p = &adc_buf[h * HALF];
        uint64_t sa = 0, sb = 0, qa = 0, qb = 0;
        uint32_t mna = st.min_a, mxa = st.max_a, mnb = st.min_b, mxb = st.max_b;
        /* Continuidad (T5.1): la muestra absoluta de esta mitad debe seguir a la ultima empujada; si no, se perdio
         * una mitad y el eje de tiempo del pipeline ya no vale: se desactiva y el bucle principal lo reinicia. */
        const uint32_t m0 = adc_half_idx[h] * HALF;
        if (live_enabled && pipe.n_in != 0u && m0 != pipe.base_m + pipe.n_in) {
            live_enabled = 0;
            pipe_gap = 1;
        }
        const uint8_t live = live_enabled;
        for (unsigned i = 0; i < HALF; i++) {
            uint32_t a = p[i] & 0xFFFFu, b = p[i] >> 16;
            sa += a;
            sb += b;
            qa += (uint64_t)a * a;
            qb += (uint64_t)b * b;
            if (a < mna) mna = a;
            if (a > mxa) mxa = a;
            if (b < mnb) mnb = b;
            if (b > mxb) mxb = b;
            if (live) {
                if (pipe.n_in == 0u) pipe.base_m = m0 + i;
                pipe_push(&pipe, a, b);
            }
        }
        st.sum_a += sa; st.sum_b += sb; st.sq_a += qa; st.sq_b += qb;
        st.min_a = mna; st.max_a = mxa; st.min_b = mnb; st.max_b = mxb;
        st.n += HALF;
        adc_ready[h] = 0;
    }
}

/* PPS: flanco de subida en PA1 -> CCR2 (fase = ticks desde el ultimo disparo del ADC) y posicion en el
 * flujo de muestras. Dos formas de contar, ambas se guardan para poder compararlas:
 *  - k (opcion B, la que se usa): TIM3 cuenta por hardware los TRGO de TIM2; se extiende a 32 bits con
 *    sus desbordes. Si el contador dio la vuelta pero su ISR no corrio aun, UIF esta pendiente (+1 vuelta).
 *    Si entre la captura y esta lectura hubo otro disparo (CNT < fase), se resta 1.
 *  - n_dma (opcion A): vueltas * BUF_LEN + (BUF_LEN - NDTR) del DMA; misma carrera con TC1 pendiente.
 * Las lecturas se repiten si una ISR modifico adc_cycles o tim3_ovf a mitad. */
#ifdef PPS_CALIB
void TIM6_DAC_IRQHandler(void)
{
    TIM6->SR = 0;
    TIM2->EGR = TIM_EGR_CC2G; /* captura por software: guarda CNT en CCR2 y entra en TIM2_IRQHandler */
}
#endif

void TIM3_IRQHandler(void)
{
    if (TIM3->SR & TIM_SR_UIF) {
        TIM3->SR = ~TIM_SR_UIF;
        tim3_ovf++;
    }
}

void TIM2_IRQHandler(void)
{
    if (!(TIM2->SR & TIM_SR_CC2IF)) {
        TIM2->SR = 0; /* otro evento (no habilitado): limpiar */
        return;
    }
    uint32_t phase = TIM2->CCR2; /* leer CCR2 limpia CC2IF */
    uint32_t c1, c2, o1, o2, ndtr, tc, cnt3, cnt2, cnt2a, pend;
    /* Se lee solo dentro de la zona segura del periodo [SAFE_LO, SAFE_HI]: ya paso el retardo de TIM3
     * (medido ~11 ticks tras el disparo) y el de la entrega del DMA (~271 ticks), y todavia no llega el
     * siguiente disparo. La fase ya esta guardada en CCR2, asi que esperar <1 periodo no la altera; la
     * espera maxima es ~1340 ticks = 22 us en una ISR que corre una vez por segundo. */
    do {
        while ((cnt2a = TIM2->CNT) < SAFE_LO || cnt2a > SAFE_HI) {}
        c1   = adc_cycles;
        o1   = tim3_ovf;
        ndtr = DMA1_Channel1->CNDTR;
        tc   = DMA1->ISR & DMA_ISR_TCIF1;
        cnt3 = TIM3->CNT;
        pend = TIM3->SR & TIM_SR_UIF;
        c2   = adc_cycles;
        o2   = tim3_ovf;
        cnt2 = TIM2->CNT;
    } while (c1 != c2 || o1 != o2 || cnt2 < cnt2a || cnt2 > SAFE_HI);
    uint32_t corr  = (cnt2 < phase) ? 1u : 0u; /* un disparo ocurrio entre la captura y esta lectura */
    uint32_t k     = (((o1 + (pend ? 1u : 0u)) << 16) | cnt3) - corr;
    uint32_t n_dma = (c1 + (tc ? 1u : 0u)) * BUF_LEN + (BUF_LEN - ndtr) - corr;

#ifdef PPS_CALIB
    {
        static uint32_t pk, pn, pphase, started;
        if (tc) cmp_tc++;
        if (k != n_dma) cmp_mis++;
        if (started) {
            int32_t db = (int32_t)(k - pk) * 1000 + (int32_t)phase - (int32_t)pphase - 59999;
            int32_t da = (int32_t)(n_dma - pn) * 1000 + (int32_t)phase - (int32_t)pphase - 59999;
            cmp_pairs++;
            if (db > 500 || db < -500) cmp_b_bad++;
            if (da > 500 || da < -500) cmp_a_bad++;
            int32_t adb = db < 0 ? -db : db, ada = da < 0 ? -da : da;
            if (adb > cmp_maxdev_b) cmp_maxdev_b = adb;
            if (ada > cmp_maxdev_a) cmp_maxdev_a = ada;
        }
        pk = k;
        pn = n_dma;
        pphase = phase;
        started = 1;
        return;
    }
#endif
    uint32_t next = (pps_head + 1u) % PPS_Q;
    if (next == pps_tail) {
        pps_lost++;
        return;
    }
    pps_q[pps_head].phase = phase;
    pps_q[pps_head].k     = k;
    pps_q[pps_head].n_dma = n_dma;
    pps_head = next;
}

static void block_done(unsigned half)
{
    adc_blocks++;
    if (adc_ready[half]) adc_proc_ovr++; /* el DSP no alcanzo a procesar la anterior */
    adc_half_idx[half] = adc_blocks - 1u;
    adc_ready[half] = 1;
    NVIC_SetPendingIRQ(DSP_IRQn);
}

void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *h)
{
    (void)h;
    block_done(0);
}

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *h)
{
    (void)h;
    adc_cycles++;
    block_done(1);
}

void HAL_ADC_MspInit(ADC_HandleTypeDef *h)
{
    __HAL_RCC_ADC12_CLK_ENABLE();
    if (h->Instance != ADC1) return; /* en modo dual un solo DMA (el del maestro) lee ambos ADC */

    __HAL_RCC_DMA1_CLK_ENABLE();
    hdma_adc1.Instance                 = DMA1_Channel1; /* ADC1 -> DMA1 canal 1 (RM0316, tabla de peticiones) */
    hdma_adc1.Init.Direction           = DMA_PERIPH_TO_MEMORY;
    hdma_adc1.Init.PeriphInc           = DMA_PINC_DISABLE;
    hdma_adc1.Init.MemInc              = DMA_MINC_ENABLE;
    hdma_adc1.Init.PeriphDataAlignment = DMA_PDATAALIGN_WORD; /* CDR es de 32 bits */
    hdma_adc1.Init.MemDataAlignment    = DMA_MDATAALIGN_WORD;
    hdma_adc1.Init.Mode                = DMA_CIRCULAR;
    hdma_adc1.Init.Priority            = DMA_PRIORITY_HIGH;
    HAL_DMA_Init(&hdma_adc1);
    __HAL_LINKDMA(h, DMA_Handle, hdma_adc1);
    HAL_NVIC_SetPriority(DMA1_Channel1_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
}

/* HSI/2 x PLL15 = 60 MHz (razones y fuentes en T1.2 / docs/RESULTADOS.md) o, con USE_HSE, HSE 8 MHz (bypass)
 * x PLL9 = 72 MHz: latencia de flash 2 ciclos hasta 72 MHz, APB1 = 36 MHz (maximo), ADC = AHB/4 = 18 MHz. */
static void SystemClock_Config(void)
{
    RCC_OscInitTypeDef osc = {0};
    int hse_ok = 0;
#ifdef USE_HSE
    /* Fuente externa en PF0 (D7), sin soldar nada en la placa (SB6 y SB8 ya vienen cerrados de fabrica):
     *   -DHSE_XTAL  cristal entre D7 (PF0) y D8 (PF1), cada pata con ~22 pF a GND (modo oscilador);
     *   sin HSE_XTAL: oscilador activo / generador de 3,3 V logico en D7 (modo bypass).
     * XTAL_MHZ (8 por defecto; pasar tambien -DHSE_VALUE=<Hz>U) da 72 MHz: 8 -> x9, 12 -> x6, 16 -> /2 x9, 24 -> /2 x6. */
#ifndef XTAL_MHZ
#define XTAL_MHZ 8u
#endif
    osc.OscillatorType      = RCC_OSCILLATORTYPE_HSE;
#ifdef HSE_XTAL
    osc.HSEState            = RCC_HSE_ON;
#else
    osc.HSEState            = RCC_HSE_BYPASS;
#endif
    osc.PLL.PLLState        = RCC_PLL_ON;
    osc.PLL.PLLSource       = RCC_PLLSOURCE_HSE;
#if XTAL_MHZ == 8
    osc.HSEPredivValue      = RCC_HSE_PREDIV_DIV1;
    osc.PLL.PLLMUL          = RCC_PLL_MUL9;
#elif XTAL_MHZ == 12
    osc.HSEPredivValue      = RCC_HSE_PREDIV_DIV1;
    osc.PLL.PLLMUL          = RCC_PLL_MUL6;
#elif XTAL_MHZ == 16
    osc.HSEPredivValue      = RCC_HSE_PREDIV_DIV2;
    osc.PLL.PLLMUL          = RCC_PLL_MUL9;
#elif XTAL_MHZ == 24
    osc.HSEPredivValue      = RCC_HSE_PREDIV_DIV2;
    osc.PLL.PLLMUL          = RCC_PLL_MUL6;
#else
#error "XTAL_MHZ no soportado: usa 8, 12, 16 o 24 (da 72 MHz exactos)"
#endif
    if (HAL_RCC_OscConfig(&osc) == HAL_OK) {   /* espera HSERDY (100 ms); HAL_TIMEOUT si no hay reloj */
        hse_ok = 1;
        clk_timer_hz = 72000000u;
        clk_sample_ticks = 1200u;
        clk_src = "HSE";
    }
#endif
    if (!hse_ok) {
        /* HSI/2 x PLL15 = 60 MHz (razones y fuentes en T1.2 / docs/RESULTADOS.md). Si venia de un intento de HSE
         * fallido se apaga el HSE. */
        RCC_OscInitTypeDef h = {0};
        h.OscillatorType      = RCC_OSCILLATORTYPE_HSI | RCC_OSCILLATORTYPE_HSE;
        h.HSEState            = RCC_HSE_OFF;
        h.HSIState            = RCC_HSI_ON;
        h.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
        h.PLL.PLLState        = RCC_PLL_ON;
        h.PLL.PLLSource       = RCC_PLLSOURCE_HSI;
        h.PLL.PLLMUL          = RCC_PLL_MUL15;
        if (HAL_RCC_OscConfig(&h) != HAL_OK) {
            for (;;) {}
        }
        clk_timer_hz = 60000000u;
        clk_sample_ticks = 1000u;
        clk_src = "HSI";
    }

    RCC_ClkInitTypeDef clk = {0};
    clk.ClockType      = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                         RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource   = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider  = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV2;
    clk.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_2) != HAL_OK) {
        for (;;) {}
    }
}

static void uart_init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_USART1_CLK_ENABLE();
    __HAL_RCC_USART2_CLK_ENABLE();

    /* PA9 = USART1_TX (a RXD del GPS), PA10 = USART1_RX (desde TXD del GPS), AF7;
     * PA2 = USART2_TX (VCP), AF7. Pinout del Nucleo-32 F303K8 (UM1956, Tabla 8). */
    GPIO_InitTypeDef gpio = {
        .Pin       = GPIO_PIN_9 | GPIO_PIN_10 | GPIO_PIN_2,
        .Mode      = GPIO_MODE_AF_PP,
        .Pull      = GPIO_PULLUP, /* linea en reposo a 1 aunque el GPS no este conectado */
        .Speed     = GPIO_SPEED_FREQ_HIGH,
        .Alternate = GPIO_AF7_USART1,
    };
    HAL_GPIO_Init(GPIOA, &gpio); /* AF7 es la misma para USART1 y USART2 en estos pines */

    huart1.Instance        = USART1;
    huart1.Init.BaudRate   = 9600; /* por defecto del NEO-7M */
    huart1.Init.WordLength = UART_WORDLENGTH_8B;
    huart1.Init.StopBits   = UART_STOPBITS_1;
    huart1.Init.Parity     = UART_PARITY_NONE;
    huart1.Init.Mode       = UART_MODE_TX_RX;
    huart1.Init.HwFlowCtl  = UART_HWCONTROL_NONE;
    HAL_UART_Init(&huart1);
    __HAL_UART_ENABLE_IT(&huart1, UART_IT_RXNE);
    HAL_NVIC_SetPriority(USART1_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(USART1_IRQn);

    /* PA15 = USART2_RX (VCP del ST-LINK, AF7); en reposo a 1 por el pull-up */
    GPIO_InitTypeDef rx2 = { .Pin = GPIO_PIN_15, .Mode = GPIO_MODE_AF_PP, .Pull = GPIO_PULLUP,
                             .Speed = GPIO_SPEED_FREQ_HIGH, .Alternate = GPIO_AF7_USART2 };
    HAL_GPIO_Init(GPIOA, &rx2);

    huart2 = huart1;
    huart2.Instance      = USART2;
    huart2.Init.BaudRate = 115200;
    huart2.Init.Mode     = UART_MODE_TX_RX;
    HAL_UART_Init(&huart2);
    __HAL_UART_ENABLE_IT(&huart2, UART_IT_RXNE);
    HAL_NVIC_SetPriority(USART2_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(USART2_IRQn);
}

/* Encola texto para el VCP sin bloquear; si la cola esta llena descarta y cuenta. */
static void vcp_write(const char *s, int len)
{
    for (int i = 0; i < len; i++) {
        uint32_t next = (tx_head + 1u) & (TX_SIZE - 1u);
        if (next == tx_tail) {
            tx_drop++;
            continue;
        }
        tx_ring[tx_head] = (uint8_t)s[i];
        tx_head = next;
    }
    USART2->CR1 |= USART_CR1_TXEIE;
}

/* T3.1/T3.2: TIM2 -> TRGO (update) -> ADC1 maestro + ADC2 esclavo simultaneos -> DMA circular */
static void sampling_init(void)
{
    /* PA0 = ADC1_IN1, PA4 = ADC2_IN1 (pinout Nucleo-32 F303K8) */
    GPIO_InitTypeDef an = { .Pin = GPIO_PIN_0 | GPIO_PIN_4, .Mode = GPIO_MODE_ANALOG, .Pull = GPIO_NOPULL };
    HAL_GPIO_Init(GPIOA, &an);

    /* Reloj del ADC: AHB/4 = 15 MHz (modo sincrono; HCLK = 60 MHz sin prescaler). Conversion de 12 bits =
     * 12,5 ciclos + muestreo 61,5 = 74 ciclos = 4,9 us, de sobra dentro de los 16,7 us de periodo.
     * El tiempo de muestreo largo (md pide >= 7,5) deja margen a una fuente de impedancia alta;
     * CONFIRMAR al conectar el front-end real. */
    hadc1.Instance                   = ADC1;
    hadc1.Init.ClockPrescaler        = ADC_CLOCK_SYNC_PCLK_DIV4;
    hadc1.Init.Resolution            = ADC_RESOLUTION_12B;
    hadc1.Init.DataAlign             = ADC_DATAALIGN_RIGHT;
    hadc1.Init.ScanConvMode          = ADC_SCAN_DISABLE;
    hadc1.Init.EOCSelection          = ADC_EOC_SINGLE_CONV;
    hadc1.Init.LowPowerAutoWait      = DISABLE;
    hadc1.Init.ContinuousConvMode    = DISABLE;
    hadc1.Init.NbrOfConversion       = 1;
    hadc1.Init.DiscontinuousConvMode = DISABLE;
    hadc1.Init.ExternalTrigConvEdge  = ADC_EXTERNALTRIGCONVEDGE_RISING;
    hadc1.Init.ExternalTrigConv      = ADC_EXTERNALTRIGCONV_T2_TRGO; /* TIM2_TRGO = EXT11 en ADC12 (RM0316) */
    hadc1.Init.DMAContinuousRequests = ENABLE;
    hadc1.Init.Overrun               = ADC_OVR_DATA_OVERWRITTEN;
    HAL_ADC_Init(&hadc1);

    hadc2 = hadc1; /* esclavo: arranca con el maestro, sin disparo propio */
    hadc2.Instance                  = ADC2;
    hadc2.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
    hadc2.Init.ExternalTrigConv     = ADC_SOFTWARE_START;
    hadc2.DMA_Handle                = NULL;
    hadc2.State                     = HAL_ADC_STATE_RESET; /* la copia trae el estado READY del maestro */
    hadc2.Lock                      = HAL_UNLOCKED;
    hadc2.ErrorCode                 = HAL_ADC_ERROR_NONE;
    HAL_ADC_Init(&hadc2);

    ADC_ChannelConfTypeDef ch = {
        .Channel      = ADC_CHANNEL_1,
        .Rank         = ADC_REGULAR_RANK_1,
        .SamplingTime = ADC_SAMPLETIME_61CYCLES_5,
        .SingleDiff   = ADC_SINGLE_ENDED,
        .OffsetNumber = ADC_OFFSET_NONE,
        .Offset       = 0,
    };
    ADC_ChannelConfTypeDef ch2 = ch;
#ifdef VREF_ON_ADC1 /* T3.4: ruido sobre VREFINT (1,2 V); RM0316: solo un ADC a la vez puede verlo */
    ch.Channel = ADC_CHANNEL_VREFINT;
#endif
#ifdef VREF_ON_ADC2
    ch2.Channel = ADC_CHANNEL_VREFINT;
#endif
    HAL_ADC_ConfigChannel(&hadc1, &ch);
    HAL_ADC_ConfigChannel(&hadc2, &ch2);

    ADC_MultiModeTypeDef mm = {
        .Mode            = ADC_DUALMODE_REGSIMULT,
        .DMAAccessMode   = ADC_DMAACCESSMODE_12_10_BITS, /* un DMA, CDR de 32 bits: ADC2 << 16 | ADC1 */
        .TwoSamplingDelay = ADC_TWOSAMPLINGDELAY_1CYCLE,
    };
    HAL_ADCEx_MultiModeConfigChannel(&hadc1, &mm);

    HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED);
    HAL_ADCEx_Calibration_Start(&hadc2, ADC_SINGLE_ENDED);

    HAL_ADC_Start(&hadc2);
    HAL_ADCEx_MultiModeStart_DMA(&hadc1, adc_buf, BUF_LEN);

    /* ISR de DSP: prioridad 3, la menor de las del sistema (DMA y PPS = 0, USART1 = 1, USART2 = 2). */
    HAL_NVIC_SetPriority(DSP_IRQn, 3, 0);
    HAL_NVIC_EnableIRQ(DSP_IRQn);

    /* TIM3 cuenta los TRGO de TIM2 (reloj externo modo 1 desde ITR1): contador de disparos exacto, sin
     * interrupciones por muestra. Se arma ANTES de TIM2 para contar tambien el UG inicial, que ya dispara
     * una conversion; asi k coincide con el numero de muestras disparadas. 16 bits + ISR de desborde. */
    __HAL_RCC_TIM3_CLK_ENABLE();
    TIM3->PSC  = 0;
    TIM3->ARR  = 0xFFFF;
    TIM3->SMCR = (CAL_ITR << TIM_SMCR_TS_Pos) | (TIM_SMCR_SMS_0 | TIM_SMCR_SMS_1 | TIM_SMCR_SMS_2);
    TIM3->DIER = TIM_DIER_UIE;
    HAL_NVIC_SetPriority(TIM3_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(TIM3_IRQn);
    TIM3->CR1  = TIM_CR1_CEN;

    /* TIM2: reloj de timer (APB1 con prescaler 2 => x2) / SAMPLE_TICKS = 60 kHz; el update genera el TRGO */
    __HAL_RCC_TIM2_CLK_ENABLE();
    htim2.Instance               = TIM2;
    htim2.Init.Prescaler         = 0;
    htim2.Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim2.Init.Period            = SAMPLE_TICKS - 1u;
    htim2.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    HAL_TIM_Base_Init(&htim2);
    TIM_MasterConfigTypeDef mc = { .MasterOutputTrigger = TIM_TRGO_UPDATE, .MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE };
    HAL_TIMEx_MasterConfigSynchronization(&htim2, &mc);

    /* T3.1: PPS en PA1 = TIM2_CH2 (AF1, confirmado con un pulso de prueba). Captura por registros: CC2
     * mapeado a TI2, flanco de subida, sin filtro ni prescaler. */
    GPIO_InitTypeDef pps = { .Pin = GPIO_PIN_1, .Mode = GPIO_MODE_AF_PP, .Pull = GPIO_NOPULL,
                             .Speed = GPIO_SPEED_FREQ_HIGH, .Alternate = GPIO_AF1_TIM2 };
    HAL_GPIO_Init(GPIOA, &pps);
    TIM2->CCMR1 = (TIM2->CCMR1 & ~(TIM_CCMR1_CC2S | TIM_CCMR1_IC2F | TIM_CCMR1_IC2PSC)) | TIM_CCMR1_CC2S_0;
    TIM2->CCER &= ~(TIM_CCER_CC2P | TIM_CCER_CC2NP);
    TIM2->CCER |= TIM_CCER_CC2E;
    TIM2->DIER |= TIM_DIER_CC2IE;
    HAL_NVIC_SetPriority(TIM2_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(TIM2_IRQn);

#ifdef PPS_CALIB
    __HAL_RCC_TIM6_CLK_ENABLE();
    TIM6->PSC  = 0;
    TIM6->ARR  = 59999 - 1; /* 59 999 ticks: la fase respecto al muestreo avanza -1 tick por captura */
    TIM6->DIER = TIM_DIER_UIE;
    HAL_NVIC_SetPriority(TIM6_DAC_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(TIM6_DAC_IRQn);
    TIM6->CR1  = TIM_CR1_CEN;
#endif

    HAL_TIM_Base_Start(&htim2);
}

#ifdef UBX_DIAG
/* Consulta UBX de solo lectura (payload vacio): B5 62 cls id 00 00 CK_A CK_B (Fletcher sobre cls..len). */
static void ubx_poll(uint8_t cls, uint8_t id)
{
    uint8_t f[8] = {0xB5, 0x62, cls, id, 0, 0, 0, 0};
    uint8_t a = 0, b = 0;
    for (int i = 2; i < 6; i++) {
        a = (uint8_t)(a + f[i]);
        b = (uint8_t)(b + a);
    }
    f[6] = a;
    f[7] = b;
    HAL_UART_Transmit(&huart1, f, sizeof f, 100);
}
#endif

/* Marca de agua de la pila (T4.4): al arrancar se pinta con 0xA5A5A5A5 toda la RAM libre entre el fin de .bss
 * y el SP; despues, los bytes que siguen intactos son el margen minimo entre heap/pila y los datos estaticos. */
extern uint32_t _end;
#define STACK_PAINT 0xA5A5A5A5u
static void stack_paint(void)
{
    uint32_t *sp;
    __asm volatile("mov %0, sp" : "=r"(sp));
    for (uint32_t *p = &_end; p < sp - 16; p++) *p = STACK_PAINT;
}
static uint32_t stack_free_min(void)
{
    uint32_t *p = &_end;
    while (p < (uint32_t *)(0x20000000u + 12u * 1024u) && *p == STACK_PAINT) p++;
    return (uint32_t)(p - &_end) * 4u;
}

/* Selector 50/60 Hz (T5.3): PB0 con pull-up interno; a GND = 50 Hz, abierto = 60 Hz. */
static uint32_t read_f0(void)
{
    return HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_0) == GPIO_PIN_RESET ? 50u : 60u;
}

/* Reinicia la cadena en vivo para la red f0 (pipe_init limpia la ventana y los CIC). */
static void live_restart(uint32_t f0)
{
    live_enabled = 0; /* el DSP no corre mientras el bucle principal ejecuta: no hay una ISR a medias */
    pipe_init(&pipe, f0, win_hi_v, win_lo_v, win_hi_i, win_lo_i);
    live_enabled = 1;
}

/* ---- Sincronia con el GPS: sello UTC (T5.1) y maquina de estados (T5.2) ------------------------------------ *
 * Linea de tiempo comun: ticks de 60 MHz nominales, T = k * 1000 + fase (k = disparos de muestreo, TIM3 por
 * hardware; el sello de un pulso es exacto, ver T3.1). Cada pulso se etiqueta con la hora de la RMC que llega
 * en los 0,5 s siguientes (T2.4: 68,8 ms, trae la hora de ese pulso); mientras no llega, la etiqueta es la del
 * pulso anterior + los segundos transcurridos. El instante de una muestra se interpola con la tasa del segundo
 * previo (unica opcion causal): con el HSI el reloj varia ~29 ppm de un segundo a otro (T2.2). */
typedef struct { uint8_t d, mo, y; uint32_t sod; } utc_t; /* dia, mes, ano (2 cifras), segundo del dia */
typedef struct { uint32_t T; utc_t utc; uint8_t has, conf; } pulse_t; /* conf: etiqueta tomada de una RMC */
enum { SY_NOSYNC = 0, SY_SYNC, SY_HOLD };
static pulse_t  pp[3];            /* pp[0] = pulso mas reciente */
static uint32_t pp_n;             /* pulsos vistos */
static uint32_t good_run;         /* pulsos consecutivos con intervalo regular */
static uint32_t tps_ref;          /* ticks por segundo del ultimo intervalo bueno (0 = aun no hay) */
static uint32_t sy_label_miss;    /* etiquetas predichas que la RMC desmintio */
static uint8_t  sy_state;

static uint8_t days_in_month(uint8_t mo, uint8_t y)
{
    static const uint8_t t[12] = { 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
    return (mo == 2u && (y % 4u) == 0u) ? 29u : t[mo - 1u]; /* 2000-2099: bisiesto cada 4 anos */
}

static void utc_add(utc_t *u, uint32_t s)
{
    u->sod += s;
    while (u->sod >= 86400u) {
        u->sod -= 86400u;
        if (++u->d > days_in_month(u->mo, u->y)) {
            u->d = 1;
            if (++u->mo > 12u) {
                u->mo = 1;
                u->y = (uint8_t)((u->y + 1u) % 100u);
            }
        }
    }
}

/* Instante actual en la linea de tiempo del muestreo (resolucion ~1 muestra, de sobra para edades de pulso). */
static uint32_t now_ticks(void)
{
    uint32_t o1, o2, cnt3, cnt2, pend;
    do {
        o1   = tim3_ovf;
        cnt3 = TIM3->CNT;
        pend = TIM3->SR & TIM_SR_UIF;
        cnt2 = TIM2->CNT;
        o2   = tim3_ovf;
    } while (o1 != o2);
    return ((((o1 + (pend ? 1u : 0u)) << 16) | cnt3) * SAMPLE_TICKS) + cnt2;
}

static void sync_on_pulse(uint32_t T)
{
    pulse_t n = { .T = T };
    if (pp_n > 0) {
        const uint32_t I = T - pp[0].T;
        const uint32_t ref = tps_ref ? tps_ref : TIMER_HZ;
        const uint32_t m = (I + ref / 2u) / ref;               /* segundos transcurridos (pulsos perdidos) */
        const int32_t err = (int32_t)(I - m * ref);
        const uint32_t tol = (tps_ref ? ref / 333u : ref / 33u) * (m ? m : 1u); /* 0,3 %; 3 % antes del 1.er intervalo */
        if (m >= 1u && m <= 5u && (uint32_t)(err < 0 ? -err : err) < tol) {
            tps_ref = I / m;
            good_run++;
            if (pp[0].has) {
                n.utc = pp[0].utc;
                utc_add(&n.utc, m);
                n.has = 1; /* etiqueta predicha; la RMC la confirma */
            }
        } else {
            good_run = 0;
        }
    }
    pp[2] = pp[1];
    pp[1] = pp[0];
    pp[0] = n;
    pp_n++;
}

static void sync_on_rmc(const nmea_t *n)
{
    if (pp_n == 0 || !n->time[0] || !n->date[0]) return;
    const uint32_t tps = tps_ref ? tps_ref : TIMER_HZ;
    if (now_ticks() - pp[0].T > tps / 2u) return; /* debe llegar en los 0,5 s siguientes al pulso */
    utc_t u;
    u.d   = (uint8_t)((n->date[0] - '0') * 10 + (n->date[1] - '0'));
    u.mo  = (uint8_t)((n->date[2] - '0') * 10 + (n->date[3] - '0'));
    u.y   = (uint8_t)((n->date[4] - '0') * 10 + (n->date[5] - '0'));
    u.sod = (uint32_t)(((n->time[0] - '0') * 10 + (n->time[1] - '0')) * 3600 +
                       ((n->time[2] - '0') * 10 + (n->time[3] - '0')) * 60 +
                       ((n->time[4] - '0') * 10 + (n->time[5] - '0')));
    if (u.d == 0u || u.mo == 0u || u.mo > 12u || u.sod >= 86400u) return;
    if (pp[0].has && !pp[0].conf && (pp[0].utc.sod != u.sod || pp[0].utc.d != u.d)) sy_label_miss++;
    pp[0].utc = u;
    pp[0].has = 1;
    pp[0].conf = 1;
}

/* SYNC: pulso en el ultimo 1,5 s, >= 3 intervalos regulares seguidos y etiqueta confirmada por una RMC.
 * HOLD: estaba sincronizado y no llega pulso (<= 5 s): se extrapola con la ultima tasa. NOSYNC: el resto. */
static void sync_update(void)
{
    const uint32_t tps = tps_ref ? tps_ref : TIMER_HZ;
    const uint32_t age = pp_n ? now_ticks() - pp[0].T : 0xFFFFFFFFu;
    const int conf = pp[0].conf || pp[1].conf;
    if (pp_n && good_run >= 3u && conf && pp[0].has && age <= tps + tps / 2u) {
        sy_state = SY_SYNC;
    } else if ((sy_state == SY_SYNC || sy_state == SY_HOLD) && pp[0].has && age <= 5u * tps) {
        sy_state = SY_HOLD;
    } else {
        sy_state = SY_NOSYNC;
    }
}

/* UTC del instante Tc (ticks): ultimo pulso anterior + (Tc - T) / (ticks por segundo del intervalo previo). */
static int sync_stamp(uint32_t Tc, utc_t *u, uint32_t *frac_us)
{
    unsigned q = 0;
    while (q < 3u && q < pp_n && (int32_t)(Tc - pp[q].T) < 0) q++;
    if (q >= 3u || q >= pp_n || !pp[q].has) return 0;
    uint32_t tps = tps_ref ? tps_ref : TIMER_HZ;
    if (q + 1u < 3u && q + 1u < pp_n) {
        const uint32_t I = pp[q].T - pp[q + 1u].T; /* tasa del segundo anterior a ese pulso */
        if (I > tps - tps / 200u && I < tps + tps / 200u) tps = I;
    }
    const uint32_t d = Tc - pp[q].T;
    const uint32_t whole = d / tps;
    *u = pp[q].utc;
    utc_add(u, whole);
    *frac_us = (uint32_t)(((uint64_t)(d - whole * tps) * 1000000u) / tps);
    return 1;
}

/* ---- Salida del fasor en unidades fisicas (T5.4) --------------------------------------------------------- */
/* Valores de ref/params.py: ZMPT101B (relacion 1:1) con Rp de 62 k (60 Hz, 120 V) o 62 k + 56 k (50 Hz, 220 V),
 * burden RB_V, filtro RF_V + C; SCT013-100 (2000:1) con burden RB_I y RF_I. kappa (calibracion de 1 punto)
 * queda en 1 hasta tener el front-end (CLAUDE.md, sec. 8). */
#define LSB_V   (3.3f / 4096.0f)
#define RB_V    470.0f
#define RF_V    3300.0f
#define RB_I    30.0f
#define RF_I    3740.0f
#define C_F     10e-9f
#define CT_N    2000.0f
#define PI_F    3.14159265358979f

/* Fasor del nodo del ADC (modulo en unidades de S = 64 * codigos, angulo en rad) -> V rms o A rms y grados.
 * Deshace la funcion de transferencia nominal del front-end y la ganancia del CIC a la frecuencia estimada. */
static void to_phys(const est_t *e, int is_v, uint32_t f0, float f, float *rms, float *ang_deg)
{
    const float rp = (f0 == 60u) ? 62e3f : 118e3f;
    const float h0 = is_v ? RB_V / rp : RB_I / CT_N;
    const float tau = C_F * (is_v ? RB_V + RF_V : RB_I + RF_I);
    const float wt = 2.0f * PI_F * f * tau;
    const float hmag = h0 / sqrtf(1.0f + wt * wt);
    const float x = PI_F * f / 60000.0f;
    const float g = sinf(4.0f * x) / (4.0f * sinf(x));
    *rms = e->mag_rms * (LSB_V / 64.0f) / (hmag * g * g * g);
    float a = (e->ang_rad + atanf(wt)) * (180.0f / PI_F); /* arg(H) = -atan(wt) */
    while (a > 180.0f) a -= 360.0f;
    while (a <= -180.0f) a += 360.0f;
    *ang_deg = a;
}

/* Escribe v con `dec` decimales (sin printf de flotantes). Devuelve los caracteres escritos. */
static int put_fixed(char *o, int cap, float v, unsigned dec)
{
    int n = 0;
    if (v < 0) {
        o[n++] = '-';
        v = -v;
    }
    uint32_t scale = 1;
    for (unsigned d = 0; d < dec; d++) scale *= 10u;
    uint32_t whole = (uint32_t)v;
    uint32_t frac = (uint32_t)((v - (float)whole) * (float)scale + 0.5f);
    if (frac >= scale) {
        whole++;
        frac -= scale;
    }
    return n + snprintf(o + n, (size_t)(cap - n), "%lu.%0*lu", (unsigned long)whole, (int)dec, (unsigned long)frac);
}

#ifdef DAC_TEST
/* Autoprueba de la cadena en vivo con una senal conocida (sin generador): el DAC1 saca dos senoidales,
 * CH1 (PA4 = A3, que es ADC2_IN1: el canal I, sin cable) y CH2 (PA5 = A4: cablear A4 -> A0 para el canal V).
 * Frecuencia DAC_TEST_MHZ (mHz), I atrasada 30 grados respecto a V, amplitudes 1241 y 620 codigos (1,0 y 0,5 V
 * pico) sobre 2048. El NCO corre desde TIM6 a 12 kHz, derivado del mismo reloj que el muestreo: el cociente
 * f_senal / f_muestreo es exacto aunque el HSI este desviado, asi que la frecuencia medida debe ser DAC_TEST_MHZ.
 * La razon DAC/ADC es ratiometrica (ambos con VDDA): codigo del ADC ~ codigo del DAC. */
#ifndef DAC_TEST_MHZ
#define DAC_TEST_MHZ 60300u
#endif
#define DAC_RATE 12000u
static int16_t  sin_q[256];
static uint32_t nco_ph, nco_inc;

static inline int32_t nco_sin(uint32_t ph) /* seno Q15 con interpolacion lineal */
{
    uint32_t i = ph >> 24, fr = (ph >> 8) & 0xFFFFu;
    int32_t a = sin_q[i], b = sin_q[(i + 1u) & 255u];
    return a + (((b - a) * (int32_t)fr) >> 16);
}

void TIM6_DAC_IRQHandler(void)
{
    TIM6->SR = 0;
    nco_ph += nco_inc;
    uint32_t ph_i = nco_ph - (uint32_t)(0x100000000ull / 12u); /* -30 grados */
    DAC1->DHR12R2 = (uint32_t)(2048 + ((1241 * nco_sin(nco_ph)) >> 15)); /* V: PA5 -> A0 */
    DAC1->DHR12R1 = (uint32_t)(2048 + ((620 * nco_sin(ph_i)) >> 15));    /* I: PA4 = ADC2_IN1 */
}

static void dac_test_init(void)
{
    for (int i = 0; i < 256; i++) sin_q[i] = (int16_t)(32767.0f * sinf(2.0f * PI_F * (float)i / 256.0f));
    nco_inc = (uint32_t)(((uint64_t)DAC_TEST_MHZ << 32) / ((uint64_t)DAC_RATE * 1000u));
    GPIO_InitTypeDef an = { .Pin = GPIO_PIN_4 | GPIO_PIN_5, .Mode = GPIO_MODE_ANALOG, .Pull = GPIO_NOPULL };
    HAL_GPIO_Init(GPIOA, &an);
    __HAL_RCC_DAC1_CLK_ENABLE();
    DAC1->DHR12R1 = 2048;
    DAC1->DHR12R2 = 2048;
    DAC1->CR = DAC_CR_EN1 | DAC_CR_EN2; /* buffer de salida activo, sin disparo: DHR -> DOR directo */
    __HAL_RCC_TIM6_CLK_ENABLE();
    TIM6->PSC = 0;
    TIM6->ARR = TIMER_HZ / DAC_RATE - 1u;
    TIM6->DIER = TIM_DIER_UIE;
    HAL_NVIC_SetPriority(TIM6_DAC_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(TIM6_DAC_IRQn);
    TIM6->CR1 = TIM_CR1_CEN;
}
#endif

int main(void)
{
    stack_paint();
    HAL_Init();
    SystemClock_Config();
    uart_init();

#ifdef UBX_DIAG
    /* Diagnostico RF (tools/ubx_diag.py): reenvia los bytes crudos del GPS sin parsear (nada de STATE
     * mezclado) y cada 3 s consulta MON-VER (solo la 1a vez), MON-HW, NAV-SVINFO y NAV-STATUS. */
    uint32_t next = HAL_GetTick() + 2000, n_poll = 0;
    for (;;) {
        while (ring_tail != ring_head) {
            uint8_t b = ring[ring_tail];
            ring_tail = (ring_tail + 1u) & (RING_SIZE - 1u);
            HAL_UART_Transmit(&huart2, &b, 1, 10);
        }
        if ((int32_t)(HAL_GetTick() - next) >= 0) {
            next += 3000;
            if (n_poll++ == 0) ubx_poll(0x0A, 0x04); /* MON-VER */
            ubx_poll(0x0A, 0x09);                    /* MON-HW */
            ubx_poll(0x01, 0x30);                    /* NAV-SVINFO */
            ubx_poll(0x01, 0x03);                    /* NAV-STATUS */
        }
    }
#endif

    __HAL_RCC_GPIOB_CLK_ENABLE();
    GPIO_InitTypeDef sel = { .Pin = GPIO_PIN_0, .Mode = GPIO_MODE_INPUT, .Pull = GPIO_PULLUP };
    HAL_GPIO_Init(GPIOB, &sel);
    uint32_t f0 = read_f0(), f0_next_check = HAL_GetTick() + 1000;
    live_restart(f0);

    sampling_init();
#ifdef DAC_TEST
    dac_test_init();
#endif

    nmea_t nmea;
    nmea_init(&nmea);
    vecrx_t vrx;
    vecrx_init(&vrx);
    vecrx_set_window(&vrx, win_hi_v, win_lo_v, win_hi_i, win_lo_i);
    int live_paused = 0;
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk; /* contador de ciclos para medir el estimador (T4.4) */
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    uint32_t gga_count = 0, ovf_reported = 0, err_reported = 0;
    uint32_t sec = 0, next_print = HAL_GetTick() + 1000, total_prev = 0, adc_ovr = 0;
    uint32_t pps_n = 0;
    uint32_t rep_seen = 0, rep_total = 0, rep_skipped = 0, rep_invalid = 0, rep_cycles = 0, rep_gaps = 0;
    char buf[128];
    vcp_write(buf, snprintf(buf, sizeof buf, "#CLK,src=%s,hz=%lu,ticks=%lu\r\n", clk_src,
                            (unsigned long)clk_timer_hz, (unsigned long)clk_sample_ticks));
    char utc_last[24] = "";
#ifdef NMEA_TS
    uint32_t cur_k = 0, cur_c = 0;
#endif
#ifdef PPS_CALIB
    uint32_t cmp_next = HAL_GetTick() + 1000;
#endif
#ifdef PPS_SELFTEST
    GPIO_InitTypeDef led = { .Pin = GPIO_PIN_3, .Mode = GPIO_MODE_OUTPUT_PP, .Pull = GPIO_NOPULL,
                             .Speed = GPIO_SPEED_FREQ_LOW };
    HAL_GPIO_Init(GPIOB, &led);
    uint32_t pulse_next = HAL_GetTick() + 1000;
    uint8_t pulse_hi = 0;
#endif
    (void)utc_last;
    for (;;) {
        /* GPS -> parser */
        while (ring_tail != ring_head) {
            uint8_t b = ring[ring_tail];
            ring_tail = (ring_tail + 1u) & (RING_SIZE - 1u);
#ifdef NMEA_ECHO
            vcp_write((const char *)&b, 1);
#endif
#ifdef NMEA_TS
            if (b == '$' && ts_tail != ts_head) {
                cur_k = ts_k[ts_tail];
                cur_c = ts_c[ts_tail];
                ts_tail = (ts_tail + 1u) & 7u;
            }
#endif
            int nr = nmea_feed(&nmea, b);
#ifdef NMEA_TS
            if (nr != NMEA_NONE) { /* NMEA,<tipo>,<k>,<cnt>,<hora>: una por sentencia (incluidas las de checksum malo) */
                const char *tm = (nr == NMEA_GGA || nr == NMEA_RMC) ? nmea.time : "";
                vcp_write(buf, snprintf(buf, sizeof buf, "NMEA,%s,%lu,%lu,%s\r\n",
                                        nr == NMEA_BAD ? "BAD" : nmea.type, (unsigned long)cur_k,
                                        (unsigned long)cur_c, tm));
            }
#endif
            if (nr == NMEA_RMC) sync_on_rmc(&nmea); /* etiqueta del ultimo pulso (T5.1) */
            if (nr == NMEA_GGA) { /* una GGA por segundo */
                int len = nmea_state_line(&nmea, buf, sizeof buf - 2);
                buf[len++] = '\r';
                buf[len++] = '\n';
                vcp_write(buf, len);
                if (++gga_count % 10 == 0) {
                    vcp_write(buf, snprintf(buf, sizeof buf, "#NMEA,ok=%lu,bad=%lu\r\n",
                                            (unsigned long)nmea.n_ok, (unsigned long)nmea.n_bad));
                    vcp_write(buf, snprintf(buf, sizeof buf, "#LIVE,f0=%lu,reports=%lu,skipped=%lu,invalid=%lu,"
                                            "cycles=%lu,gaps=%lu,sync=%u,good=%lu,tps=%lu,labmiss=%lu,clk=%s,"
                                            "hz=%lu,ticks=%lu\r\n",
                                            (unsigned long)f0, (unsigned long)rep_total,
                                            (unsigned long)rep_skipped, (unsigned long)rep_invalid,
                                            (unsigned long)rep_cycles, (unsigned long)rep_gaps, sy_state,
                                            (unsigned long)good_run, (unsigned long)tps_ref,
                                            (unsigned long)sy_label_miss, clk_src,
                                            (unsigned long)clk_timer_hz, (unsigned long)clk_sample_ticks));
                }
            }
        }

        /* Selector 50/60 Hz (T5.3): se relee cada segundo; un cambio reinicia la cadena en vivo. */
        if ((int32_t)(HAL_GetTick() - f0_next_check) >= 0) {
            f0_next_check += 1000;
            uint32_t now_f0 = read_f0();
            if (now_f0 != f0 && !live_paused) {
                f0 = now_f0;
                live_restart(f0);
                rep_seen = 0;
                vcp_write(buf, snprintf(buf, sizeof buf, "#MODE,f0=%lu\r\n", (unsigned long)f0));
            }
        }

        /* PC -> vectores de prueba (T4.1): VEC,<estado>,<n_in>,<f0>,<crc>,<sumV>,<sumI>,<minV>,<maxV>,<minI>,<maxI>
         * Mientras llega un vector el modo en vivo se pausa (comparten la ventana). */
        {
            int res = vecrx_poll(&vrx, HAL_GetTick());
            while (res == VECRX_BUSY && rx2_tail != rx2_head) {
                uint8_t b = rx2_ring[rx2_tail];
                rx2_tail = (rx2_tail + 1u) & (RX2_SIZE - 1u);
                res = vecrx_feed(&vrx, b, HAL_GetTick());
                if (!live_paused && vecrx_busy(&vrx)) {
                    live_enabled = 0;
                    live_paused = 1;
                }
            }
            if (res != VECRX_BUSY) {
                static const char *const nom[] = { "BUSY", "OK", "CRC", "HDR", "TIMEOUT" };
                vcp_write(buf, snprintf(buf, sizeof buf,
                                        "VEC,%s,%u,%u,%08lx,%lu,%lu,%u,%u,%u,%u,%lu,%lu\r\n", nom[res],
                                        vrx.n_in, vrx.f0, (unsigned long)vrx.crc_calc,
                                        (unsigned long)vrx.sum_v, (unsigned long)vrx.sum_i, vrx.min_v, vrx.max_v,
                                        vrx.min_i, vrx.max_i, (unsigned long)rx2_overflow,
                                        (unsigned long)rx2_errors));
                if (res == VECRX_OK) { /* T4.2: salida del CIC entero (S = 64 * codigo filtrado) */
                    vcp_write(buf, snprintf(buf, sizeof buf, "CIC,%lu,%08lx,%lu,%lu,%ld,%ld,%ld,%ld\r\n",
                                            (unsigned long)vrx.n_out, (unsigned long)vrx.crc_s,
                                            (unsigned long)vrx.sum_sv, (unsigned long)vrx.sum_si,
                                            (long)vrx.first_sv, (long)vrx.first_si, (long)vrx.last_sv,
                                            (long)vrx.last_si));
                    /* T4.3: estimador (IpDFT + minimos cuadrados) sobre la ventana de 4 ciclos.
                     * EST,<f_V uHz>,<f_I uHz>,<mag_V nV rms>,<ang_V udeg>,<mag_I nV rms>,<ang_I udeg>,<ciclos> */
                    est_t ev, ei;
                    uint32_t c0 = DWT->CYCCNT;
                    int e1 = est_run(win_hi_v, win_lo_v, vrx.n_out, 0u, vrx.n_out, 15000.0f, 4u, &ev);
                    int e2 = est_run(win_hi_i, win_lo_i, vrx.n_out, 0u, vrx.n_out, 15000.0f, 4u, &ei);
                    uint32_t cyc = DWT->CYCCNT - c0;
#ifdef EST_PROFILE
                    {
                        extern uint32_t est_prof[8];
                        vcp_write(buf, snprintf(buf, sizeof buf, "PROF,tab=%lu,sum=%lu,dft=%lu,cinit=%lu,fit=%lu,sweep=%lu\r\n",
                                                (unsigned long)est_prof[0], (unsigned long)est_prof[1],
                                                (unsigned long)est_prof[2], (unsigned long)est_prof[4],
                                                (unsigned long)est_prof[5], (unsigned long)est_prof[6]));
                        for (int q = 0; q < 8; q++) est_prof[q] = 0;
                    }
#endif
                    if (e1 == 0 && e2 == 0) {
                        const double k_v = 3.3 / 4096.0 / 64.0 * 1e9; /* S -> nV en el nodo del ADC */
                        const double r2d = 57.29577951308232 * 1e6;   /* rad -> udeg */
                        vcp_write(buf, snprintf(buf, sizeof buf, "EST,%ld,%ld,%ld,%ld,%ld,%ld,%lu\r\n",
                                                (long)((double)ev.f_hz * 1e6), (long)((double)ei.f_hz * 1e6),
                                                (long)((double)ev.mag_rms * k_v), (long)((double)ev.ang_rad * r2d),
                                                (long)((double)ei.mag_rms * k_v), (long)((double)ei.ang_rad * r2d),
                                                (unsigned long)cyc));
                    } else {
                        vcp_write(buf, snprintf(buf, sizeof buf, "EST,ERROR,%d,%d\r\n", e1, e2));
                    }
                    /* MEM,<bytes libres minimos entre .bss y la pila (RAM de 12 KB)> */
                    vcp_write(buf, snprintf(buf, sizeof buf, "MEM,%lu\r\n", (unsigned long)stack_free_min()));
                }
            }
            if (res != VECRX_BUSY && live_paused) { /* vector terminado (bien, mal o por timeout): vuelve el modo vivo */
                live_paused = 0;
                live_restart(f0);
                rep_seen = 0;
            }
        }

        /* Hueco en las muestras (una mitad del DMA se perdio): el eje de tiempo del pipeline ya no vale. */
        if (pipe_gap) {
            pipe_gap = 0;
            rep_gaps++;
            live_restart(f0);
            rep_seen = 0;
        }

        /* Reporte en vivo (T5.3/T5.4): cada `period` salidas del CIC, sobre las N mas recientes. */
        if (live_enabled) {
            uint32_t start, n_at, skipped;
            if (pipe_take(&pipe, &rep_seen, &start, &n_at, &skipped)) {
                rep_skipped += skipped;
                est_t ev, ei;
                uint32_t c0 = DWT->CYCCNT;
                int e1 = est_run(win_hi_v, win_lo_v, pipe.len, start, pipe.n, 15000.0f, 4u, &ev);
                int e2 = est_run(win_hi_i, win_lo_i, pipe.len, start, pipe.n, 15000.0f, 4u, &ei);
                rep_cycles = DWT->CYCCNT - c0;
                if (e1 == 0 && e2 == 0 && pipe_window_valid(&pipe, n_at) && live_enabled) {
                    rep_total++;
                    sync_update();
                    /* El estimador mide en unidades del reloj de muestreo; con el PPS se conoce su error
                     * (-1126 ppm con HSI = 68 mHz a 60 Hz) y la frecuencia fisica es f * tps / TIMER_HZ. */
                    /* Promedio de V e I ponderado por la energia de cada canal (la varianza de la frecuencia
                     * escala con 1/amplitud^2): un canal sin senal (V flotante, I sin carga) no arrastra el ruido. */
                    const float wv = ev.mag_rms * ev.mag_rms, wi = ei.mag_rms * ei.mag_rms;
                    float f = (wv + wi > 0.0f) ? (ev.f_hz * wv + ei.f_hz * wi) / (wv + wi) : 0.5f * (ev.f_hz + ei.f_hz);
                    if (sy_state != SY_NOSYNC && tps_ref) f *= (float)tps_ref / (float)TIMER_HZ;
                    float vr, va, ir, ia;
                    to_phys(&ev, 1, f0, f, &vr, &va);
                    to_phys(&ei, 0, f0, f, &ir, &ia);
                    /* PMU,<utc>,<f_Hz>,<V_rms>,<V_ang_deg>,<I_rms>,<I_ang_deg>,<bandera>
                     * utc = instante del CENTRO de la ventana (T5.1): sin pulso confiable, campo vacio y NOSYNC. */
                    char ut[28] = "";
                    const uint32_t j0 = n_at - pipe.n;
                    const uint32_t Tc = (2u * pipe.base_m + 11u + 8u * j0 + 4u * (pipe.n - 1u)) * (SAMPLE_TICKS / 2u);
                    utc_t uu;
                    uint32_t fus;
                    if (sy_state != SY_NOSYNC && sync_stamp(Tc, &uu, &fus)) {
                        snprintf(ut, sizeof ut, "%02u%02u%02uT%02lu%02lu%02lu.%06lu", uu.d, uu.mo, uu.y,
                                 (unsigned long)(uu.sod / 3600u), (unsigned long)((uu.sod / 60u) % 60u),
                                 (unsigned long)(uu.sod % 60u), (unsigned long)fus);
                    }
                    const char *flag = !ut[0] ? "NOSYNC" : (sy_state == SY_SYNC ? "SYNC" : "HOLD");
                    int n = snprintf(buf, sizeof buf, "PMU,%s,", ut);
                    n += put_fixed(buf + n, (int)sizeof buf - n, f, 4);
                    buf[n++] = ',';
                    n += put_fixed(buf + n, (int)sizeof buf - n, vr, 3);
                    buf[n++] = ',';
                    n += put_fixed(buf + n, (int)sizeof buf - n, va, 3);
                    buf[n++] = ',';
                    n += put_fixed(buf + n, (int)sizeof buf - n, ir, 4);
                    buf[n++] = ',';
                    n += put_fixed(buf + n, (int)sizeof buf - n, ia, 3);
                    n += snprintf(buf + n, sizeof buf - (size_t)n, ",%s\r\n", flag);
                    vcp_write(buf, n);
                } else {
                    rep_invalid++;
                }
            }
        }

        /* ADC: estadistica de la ultima ventana de 1 s (la acumula la ISR de DSP) */
        if (__HAL_ADC_GET_FLAG(&hadc1, ADC_FLAG_OVR) || __HAL_ADC_GET_FLAG(&hadc2, ADC_FLAG_OVR)) {
            adc_ovr++;
            __HAL_ADC_CLEAR_FLAG(&hadc1, ADC_FLAG_OVR);
            __HAL_ADC_CLEAR_FLAG(&hadc2, ADC_FLAG_OVR);
        }

        if ((int32_t)(HAL_GetTick() - next_print) >= 0) {
            next_print += 1000;
            uint64_t sum_a, sum_b, sq_a, sq_b;
            uint32_t n, min_a, max_a, min_b, max_b;
            NVIC_DisableIRQ(DSP_IRQn); /* instantanea coherente: el DSP no corre mientras se copia y reinicia */
            sum_a = st.sum_a; sum_b = st.sum_b; sq_a = st.sq_a; sq_b = st.sq_b; n = st.n;
            min_a = st.min_a; max_a = st.max_a; min_b = st.min_b; max_b = st.max_b;
            st.sum_a = st.sum_b = st.sq_a = st.sq_b = 0;
            st.n = 0;
            st.min_a = st.min_b = 0xFFFF;
            st.max_a = st.max_b = 0;
            NVIC_EnableIRQ(DSP_IRQn);

            uint32_t total = adc_blocks * HALF;
            uint32_t cnt = n ? n : 1;
            uint32_t ma = (uint32_t)(sum_a * 10 / cnt), mb = (uint32_t)(sum_b * 10 / cnt);
            /* desviacion estandar (LSB x100) en doble precision; una vez por segundo, el costo no importa */
            double va = ((double)sq_a * cnt - (double)sum_a * (double)sum_a) / ((double)cnt * cnt);
            double vb = ((double)sq_b * cnt - (double)sum_b * (double)sum_b) / ((double)cnt * cnt);
            uint32_t sa = (uint32_t)(sqrt(va > 0 ? va : 0) * 100.0 + 0.5);
            uint32_t sb = (uint32_t)(sqrt(vb > 0 ? vb : 0) * 100.0 + 0.5);
            vcp_write(buf, snprintf(buf, sizeof buf,
                                    "ADC,%lu,%lu,%lu,%lu,%lu,%lu,%lu.%lu/%lu/%lu/%lu.%02lu,%lu.%lu/%lu/%lu/%lu.%02lu\r\n",
                                    (unsigned long)sec++, (unsigned long)total, (unsigned long)(total - total_prev),
                                    (unsigned long)adc_ovr, (unsigned long)adc_proc_ovr, (unsigned long)tx_drop,
                                    (unsigned long)(ma / 10), (unsigned long)(ma % 10),
                                    (unsigned long)(n ? min_a : 0), (unsigned long)max_a,
                                    (unsigned long)(sa / 100), (unsigned long)(sa % 100),
                                    (unsigned long)(mb / 10), (unsigned long)(mb % 10),
                                    (unsigned long)(n ? min_b : 0), (unsigned long)max_b,
                                    (unsigned long)(sb / 100), (unsigned long)(sb % 100)));
            total_prev = total;
        }

        /* PPS,<n>,<fase>,<k>,<n_dma>: k = muestras disparadas hasta el pulso (opcion B, exacta);
         * n_dma = entregadas por el DMA (opcion A); k - n_dma = 0 o 1 segun la fase (umbral ~271). */
        while (pps_tail != pps_head) {
            pps_rec_t r = pps_q[pps_tail];
            pps_tail = (pps_tail + 1u) % PPS_Q;
            sync_on_pulse(r.k * SAMPLE_TICKS + r.phase);
            vcp_write(buf, snprintf(buf, sizeof buf, "PPS,%lu,%lu,%lu,%lu\r\n", (unsigned long)pps_n++,
                                    (unsigned long)r.phase, (unsigned long)r.k, (unsigned long)r.n_dma));
        }
#ifdef PPS_CALIB
        if ((int32_t)(HAL_GetTick() - cmp_next) >= 0) {
            cmp_next += 1000;
            /* PPSCMP,<pares>,<A_mal>,<B_mal>,<k!=n_dma>,<TC_pendiente>,<desv_max_B>,<desv_max_A> */
            vcp_write(buf, snprintf(buf, sizeof buf, "PPSCMP,%lu,%lu,%lu,%lu,%lu,%ld,%ld\r\n",
                                    (unsigned long)cmp_pairs, (unsigned long)cmp_a_bad,
                                    (unsigned long)cmp_b_bad, (unsigned long)cmp_mis,
                                    (unsigned long)cmp_tc, (long)cmp_maxdev_b, (long)cmp_maxdev_a));
        }
#endif
        if (pps_lost) {
            vcp_write(buf, snprintf(buf, sizeof buf, "#PPSLOST,%lu\r\n", (unsigned long)pps_lost));
            pps_lost = 0;
        }
#ifdef PPS_SELFTEST
        /* Pulso de prueba en PB3 (LD3, D13) cada 1000 ms, 100 ms de ancho: cablear D13 -> A1 (PA1). */
        uint32_t now = HAL_GetTick();
        if (!pulse_hi && (int32_t)(now - pulse_next) >= 0) {
            GPIOB->BSRR = GPIO_PIN_3;
#ifdef PPS_SW
            TIM2->EGR = TIM_EGR_CC2G; /* captura por software: prueba sin cable ni PA1 */
#endif
            pulse_hi = 1;
            pulse_next += 100;
        } else if (pulse_hi && (int32_t)(now - pulse_next) >= 0) {
            GPIOB->BSRR = (uint32_t)GPIO_PIN_3 << 16;
            pulse_hi = 0;
            pulse_next += 900;
        }
#endif

        /* Avisos de perdida del GPS: lineas con '#' no se confunden con STATE ni con NMEA ('$'). */
        if (ring_overflow != ovf_reported || uart_errors != err_reported) {
            ovf_reported = ring_overflow;
            err_reported = uart_errors;
            vcp_write(buf, snprintf(buf, sizeof buf, "#GPSRX,ovf=%lu,err=%lu\r\n",
                                    (unsigned long)ovf_reported, (unsigned long)err_reported));
        }
    }
}
