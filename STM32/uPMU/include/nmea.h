/* T1.4: parser NMEA minimo (GGA y RMC) sin dependencias del HAL, byte a byte.
 * Se alimenta desde el bucle principal, nunca desde una ISR (regla 7). */
#ifndef NMEA_H
#define NMEA_H

#include <stddef.h>
#include <stdint.h>

#define NMEA_LINE_MAX 96 /* NMEA 0183 limita a 82; $GPTXT de u-blox cabe de sobra */

typedef struct {
    /* acumulador de la sentencia en curso */
    char    line[NMEA_LINE_MAX];
    uint8_t len;
    uint8_t in_sentence; /* hemos visto '$' y no el fin de linea */
    uint8_t dirty;       /* caracter no imprimible o linea demasiado larga */

    /* ultimos valores validos */
    char    time[11];   /* "hhmmss.ss" de la ultima GGA/RMC con hora; "" si no hay */
    char    date[7];    /* "ddmmyy" de la ultima RMC; "" si no hay */
    char    rmc_status; /* 'A' valido, 'V' invalido, 0 sin RMC */
    uint8_t fix;        /* GGA: calidad de fix (0 = sin fix) */
    uint8_t sats;       /* GGA: satelites usados */

    /* contadores */
    uint32_t n_ok;  /* sentencias con checksum correcto */
    uint32_t n_bad; /* checksum malo, sin '*', demasiado larga o con basura */

    char    type[4];    /* tipo (3 letras, sin talker) de la ultima sentencia con checksum correcto: "GGA", "RMC"... */
} nmea_t;

/* Resultado de nmea_feed */
enum { NMEA_NONE = 0, NMEA_OK = 1, NMEA_GGA = 2, NMEA_RMC = 3, NMEA_BAD = -1 };

void nmea_init(nmea_t *n);
/* Devuelve NMEA_NONE mientras la sentencia no termine; al terminar, el tipo o NMEA_BAD. */
int  nmea_feed(nmea_t *n, uint8_t c);
/* "<ddmmyy>T<hhmmss.ss>,<fix>,<sats>" (fecha desconocida = "------"; sin hora = campo vacio). */
int  nmea_state_line(const nmea_t *n, char *out, size_t size);

#endif
