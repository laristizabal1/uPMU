/* T4.1: receptor de vectores de prueba por el puerto serie (PC -> Nucleo), byte a byte, sin HAL.
 *
 * Trama (little endian):
 *   0x55 0x56 | n_in u16 | f0 u8 (50/60) | flags u8 | n_in * { V u16, I u16 } | CRC32 u32 (del payload)
 * Los codigos son los del ADC de 12 bits a 60 kS/s (entrada del CIC de T4.2). No se guardan: se procesan
 * en flujo (memoria: el F303K8 no tiene RAM para 16-19 KB). Por ahora solo estadistica y CRC. */
#ifndef VECRX_H
#define VECRX_H

#include <stdint.h>
#include "cic.h"

#define VECRX_N_MAX 6000u /* 4818 muestras en 50 Hz; con margen */

enum { VECRX_BUSY = 0, VECRX_OK = 1, VECRX_CRC = 2, VECRX_HDR = 3, VECRX_TIMEOUT = 4 };

typedef struct {
    /* maquina de estados */
    uint8_t  state;
    uint8_t  idx;        /* posicion dentro del campo actual */
    uint8_t  buf[4];     /* acumulador de cabecera / muestra / CRC */
    uint32_t t_last;     /* ms del ultimo byte (timeout) */
    uint32_t got;        /* muestras recibidas */
    uint32_t crc;        /* CRC32 corriendo del payload */
    uint32_t crc_rx;

    /* cabecera de la trama en curso */
    uint16_t n_in;
    uint8_t  f0;
    uint8_t  flags;

    /* resultado (valido al terminar) */
    uint32_t crc_calc;
    uint32_t sum_v, sum_i;
    uint16_t min_v, max_v, min_i, max_i;

    /* T4.2: salida del CIC (entero S = 64 * codigo filtrado), ventana de 4 ciclos = 60000 / f0 salidas */
    cic_t    cic_v, cic_i;
    uint32_t n_out_max;                 /* 1000 a 60 Hz, 1200 a 50 Hz */
    uint32_t n_out;                     /* salidas acumuladas */
    uint32_t crc_s;                     /* CRC32 de las salidas (int32 LE, V e I intercalados) */
    uint32_t sum_sv, sum_si;
    int32_t  first_sv, first_si, last_sv, last_si;

    /* T4.3: ventana de S para el estimador (S exacto: hi = S >> 2, lo = 2 bits bajos, ver estimator.h).
     * Los asigna el dueño con vecrx_set_window(); si son NULL no se guarda nada. */
    uint16_t *hi_v, *hi_i;
    uint8_t  *lo_v, *lo_i;
} vecrx_t;

void vecrx_set_window(vecrx_t *r, uint16_t *hi_v, uint8_t *lo_v, uint16_t *hi_i, uint8_t *lo_i);

void vecrx_init(vecrx_t *r);
/* 1 si hay una trama a medias (o un byte de sincronia ya visto). */
int  vecrx_busy(const vecrx_t *r);
/* Devuelve VECRX_BUSY mientras la trama no termine; al terminar, VECRX_OK/CRC/HDR. Tras un resultado != BUSY
 * el receptor queda listo para la siguiente trama (los datos del resultado siguen validos hasta la proxima). */
int  vecrx_feed(vecrx_t *r, uint8_t c, uint32_t now_ms);
/* Llamar periodicamente: si hay una trama a medias y pasaron > VECRX_TIMEOUT_MS sin bytes, la aborta. */
int  vecrx_poll(vecrx_t *r, uint32_t now_ms);

#define VECRX_TIMEOUT_MS 500u

#endif
