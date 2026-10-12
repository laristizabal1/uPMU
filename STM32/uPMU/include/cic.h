/* T4.2: CIC de orden 3, R = 4 (60 -> 15 kS/s), aritmetica entera.
 *
 * H(z) = ((1 - z^-4) / (1 - z^-1))^3 = conv([1 1 1 1] x3) con ganancia DC 64 (sin normalizar).
 * Integradores a 60 kS/s y peines a 15 kS/s con aritmetica modular de 32 bits: el resultado es exacto porque
 * la salida real cabe en 18 bits (4095 * 64 = 262 080). Equivale a la convolucion con ceros previos de
 * ref/simulate_chain.py (np.convolve(c, H_CIC) / 64); aqui la salida es el entero S = 64 * H_CIC * c, sin
 * redondeo. El retardo de grupo es (10 - 1) / 2 = 4,5 muestras de 60 kS/s = 75 us. */
#ifndef CIC_H
#define CIC_H

#include <stdint.h>

#define CIC_R        4u
#define CIC_FIRST    9u /* indice (base 0) de la primera salida con las 10 taps completas, como en ref */
#define CIC_PHASE    1u /* las salidas caen en indices de entrada = CIC_PHASE (mod R), como en ref */

typedef struct {
    uint32_t i1, i2, i3; /* integradores */
    uint32_t c1, c2, c3; /* retardos de los peines */
    uint32_t n;          /* muestras de entrada consumidas */
} cic_t;

void cic_init(cic_t *c);
/* Consume una muestra (0..4095). Devuelve 1 y escribe *y cuando hay una salida valida (descarta el
 * transitorio inicial: las salidas con indice < CIC_FIRST). */
int  cic_push(cic_t *c, uint32_t x, int32_t *y);

#endif
