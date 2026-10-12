#include "nmea.h"
#include <stdio.h>
#include <string.h>

static int hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

/* Copia un campo de hora/fecha solo si tiene el largo y los caracteres esperados. */
static void copy_field(char *dst, size_t dst_size, const char *src, size_t min_len, int allow_dot)
{
    size_t i = 0;
    while (src[i] && i < dst_size - 1) {
        char c = src[i];
        if (!((c >= '0' && c <= '9') || (allow_dot && c == '.'))) { i = 0; break; }
        i++;
    }
    if (i < min_len) i = 0;
    memcpy(dst, src, i);
    dst[i] = '\0';
}

static uint8_t to_u8(const char *s)
{
    unsigned v = 0;
    while (*s >= '0' && *s <= '9' && v < 255) v = v * 10 + (unsigned)(*s++ - '0');
    return (uint8_t)(v > 255 ? 255 : v);
}

/* Procesa una sentencia ya validada. 'body' es lo que hay entre '$' y '*'; se modifica (coma -> 0). */
static int parse_body(nmea_t *n, char *body)
{
    char *f[16];
    size_t nf = 0;
    for (char *p = body; nf < 16;) {
        f[nf++] = p;
        p = strchr(p, ',');
        if (!p) break;
        *p++ = '\0';
    }
    size_t alen = strlen(f[0]);
    if (alen < 5) {
        strcpy(n->type, "?");
        return NMEA_OK;
    }
    const char *type = f[0] + alen - 3; /* ignora el talker: GP, GN, GL... */
    memcpy(n->type, type, 3);
    n->type[3] = 0;

    if (!strcmp(type, "GGA") && nf >= 8) {
        copy_field(n->time, sizeof n->time, f[1], 6, 1);
        n->fix  = to_u8(f[6]);
        n->sats = to_u8(f[7]);
        return NMEA_GGA;
    }
    if (!strcmp(type, "RMC") && nf >= 10) {
        copy_field(n->time, sizeof n->time, f[1], 6, 1);
        n->rmc_status = (f[2][0] == 'A' || f[2][0] == 'V') ? f[2][0] : 0;
        copy_field(n->date, sizeof n->date, f[9], 6, 0);
        return NMEA_RMC;
    }
    return NMEA_OK;
}

static int finish(nmea_t *n)
{
    n->in_sentence = 0;
    n->line[n->len] = '\0';
    char *star = memchr(n->line, '*', n->len);
    int cs_hi, cs_lo;
    if (n->dirty || !star || (size_t)(n->line + n->len - star) != 3 ||
        (cs_hi = hexval(star[1])) < 0 || (cs_lo = hexval(star[2])) < 0) {
        n->n_bad++;
        return NMEA_BAD;
    }
    uint8_t x = 0;
    for (const char *p = n->line; p < star; p++) x ^= (uint8_t)*p;
    if (x != (uint8_t)(cs_hi << 4 | cs_lo)) {
        n->n_bad++;
        return NMEA_BAD;
    }
    *star = '\0';
    n->n_ok++;
    return parse_body(n, n->line);
}

void nmea_init(nmea_t *n)
{
    memset(n, 0, sizeof *n);
}

int nmea_feed(nmea_t *n, uint8_t c)
{
    if (c == '$') { /* inicio (o resincronizacion si la anterior quedo a medias) */
        if (n->in_sentence) n->n_bad++;
        n->in_sentence = 1;
        n->len = 0;
        n->dirty = 0;
        return NMEA_NONE;
    }
    if (!n->in_sentence) return NMEA_NONE;

    if (c == '\r' || c == '\n') {
        return n->len ? finish(n) : NMEA_NONE;
    }
    if (c < 0x20 || c > 0x7E || n->len >= NMEA_LINE_MAX - 1) {
        n->dirty = 1; /* se sigue hasta el fin de linea para no perder la sincronia */
        return NMEA_NONE;
    }
    n->line[n->len++] = (char)c;
    return NMEA_NONE;
}

int nmea_state_line(const nmea_t *n, char *out, size_t size)
{
    return snprintf(out, size, "STATE,%s%s%s,%u,%u",
                    n->time[0] ? (n->date[0] ? n->date : "------") : "",
                    n->time[0] ? "T" : "",
                    n->time,
                    (unsigned)n->fix, (unsigned)n->sats);
}
