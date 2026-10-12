/* T4.3: IpDFT (ventana Hann) + ajuste sinusoidal por minimos cuadrados con refinamiento Gauss-Newton.
 * Replica ipdft_ls() de ref/simulate_chain.py (referencia en float64) en C, sin dependencias del HAL.
 *
 * Entrada: ventana de N muestras uniformes a fs, la salida entera S del CIC (18 bits, T4.2; offset DC incluido,
 * se resta) guardada en dos arreglos para ahorrar RAM: hi[n] = S >> 2 (uint16) y lo[n >> 2] con los 2 bits bajos
 * de 4 muestras por byte. Asi se conserva S exacto en 2,25 bytes por muestra (frente a 4 en int32).
 * Salida (por canal): frecuencia, modulo rms y angulo del fasor en el centro de la ventana, en las
 * unidades de S (= 64 * codigos del ADC). */
#ifndef ESTIMATOR_H
#define ESTIMATOR_H

#include <stdint.h>

#ifdef EST_DOUBLE
typedef double est_real;
#else
typedef float est_real;
#endif

typedef struct {
    est_real f_hz;     /* frecuencia estimada */
    est_real mag_rms;  /* modulo rms del fasor (misma unidad que la entrada) */
    est_real ang_rad;  /* angulo en el centro de la ventana: y = Re{ sqrt(2) * mag * e^{j(w tau + ang)} } */
} est_t;

#define EST_N_MAX   1200u
#define EST_LO_BYTES(n) (((n) + 3u) / 4u)
#ifndef EST_ITER
/* Iteraciones de Gauss-Newton: ref usa 4, pero con 1 el error ya es < 0,01 mHz y con 2 el resultado en double es
 * identico al de 4 (medido con los 14 vectores, tools/test_est.py); se dejan 2. */
#define EST_ITER    2u
#endif

/* k0 = round(f0 * N / fs) = 4 (4 ciclos en la ventana; es el unico valor soportado). Devuelve 0 si ok. */
/* La ventana son las n muestras que empiezan en `start` dentro de un buffer circular de `len` (len >= n). */
int est_run(const uint16_t *hi, const uint8_t *lo, uint32_t len, uint32_t start, uint32_t n, est_real fs,
            uint32_t k0, est_t *out);

/* Guarda S (0..262143) en la posicion n de (hi, lo). `lo` debe estar a cero antes de la primera escritura. */
static inline void est_store(uint16_t *hi, uint8_t *lo, uint32_t n, uint32_t s)
{
    hi[n] = (uint16_t)(s >> 2);
    lo[n >> 2] = (uint8_t)((lo[n >> 2] & ~(3u << (2u * (n & 3u)))) | ((s & 3u) << (2u * (n & 3u))));
}
static inline uint32_t est_load(const uint16_t *hi, const uint8_t *lo, uint32_t n)
{
    return ((uint32_t)hi[n] << 2) | ((lo[n >> 2] >> (2u * (n & 3u))) & 3u);
}

#endif
