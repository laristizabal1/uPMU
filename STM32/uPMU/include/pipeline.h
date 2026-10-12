/* T5: cadena en tiempo real, sin HAL: pares de muestras del ADC a 60 kS/s -> CIC (T4.2) -> ventana circular de S
 * exacto (hi/lo, ver estimator.h) -> disparo periodico de reportes para el estimador (T4.3).
 *
 * La ventana tiene N salidas (4 ciclos: 1000 a 60 Hz, 1200 a 50 Hz) y se reporta cada `period` salidas
 * (500 a 60 Hz = 30 fps; 600 a 50 Hz = 25 fps). El buffer circular mide N + slack: mientras el estimador lee la
 * ventana (~20 ms = ~300 salidas a 15 kS/s) siguen llegando salidas nuevas y no deben pisarla. */
#ifndef PIPELINE_H
#define PIPELINE_H

#include <stdint.h>
#include "cic.h"

#define PIPE_SLACK   600u                    /* 40 ms de salidas a 15 kS/s: el estimador tarda ~24 ms (60 Hz) o ~30 ms (50 Hz) */
#define PIPE_N_MAX   1200u
#define PIPE_LEN_MAX (PIPE_N_MAX + PIPE_SLACK)

typedef struct {
    /* configuracion */
    uint32_t n;       /* salidas por ventana */
    uint32_t period;  /* salidas entre reportes */
    uint32_t len;     /* largo del buffer circular = n + PIPE_SLACK */
    uint16_t *hi_v, *hi_i;
    uint8_t  *lo_v, *lo_i;

    /* estado (lo escribe pipe_push, normalmente desde una ISR) */
    cic_t    cic_v, cic_i;
    uint32_t wp;        /* proximo indice de escritura */
    uint32_t n_out;     /* salidas producidas desde pipe_init (envuelve a 2^32) */
    uint32_t next_due;  /* n_out al que toca el siguiente reporte */

    /* buzon del ultimo disparo: el consumidor lo lee con pipe_take() */
    volatile uint32_t rep_seq;     /* se incrementa en cada disparo */
    uint32_t rep_start;            /* indice inicial de la ventana de ese disparo */
    uint32_t rep_n_out;            /* n_out en el disparo */

    /* T5.1: ubicacion en la linea de tiempo del muestreo. El caller fija base_m (indice absoluto, base 0, de la
     * primera muestra entregada al pipeline) antes del primer pipe_push; n_in cuenta las muestras empujadas. */
    uint32_t n_in;
    uint32_t base_m;
} pipe_t;

/* f0 = 50 o 60. El caller entrega los arreglos, de al menos PIPE_LEN_MAX (hi) y (PIPE_LEN_MAX + 3) / 4 (lo). */
int  pipe_init(pipe_t *p, uint32_t f0, uint16_t *hi_v, uint8_t *lo_v, uint16_t *hi_i, uint8_t *lo_i);
/* Una pareja de muestras (V, I) de 12 bits a 60 kS/s. */
void pipe_push(pipe_t *p, uint32_t v, uint32_t i);

/* Lee el ultimo disparo de forma coherente (no atomico respecto a la ISR). Devuelve 1 y llena start/seq/n_out_at
 * si hay un disparo nuevo respecto a *seen; en *seen deja la secuencia leida. `skipped` cuenta disparos que llegaron
 * y no se consumieron (el estimador fue mas lento que el periodo). */
int  pipe_take(pipe_t *p, uint32_t *seen, uint32_t *start, uint32_t *n_out_at, uint32_t *skipped);
/* Tras estimar: 1 si la ventana sigue intacta (no llegaron mas de PIPE_SLACK salidas desde el disparo). */
int  pipe_window_valid(const pipe_t *p, uint32_t n_out_at);

#endif
