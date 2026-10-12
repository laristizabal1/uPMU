#include "vecrx.h"
#include "estimator.h"
#include <string.h>

enum { S_SYNC0, S_SYNC1, S_HDR, S_DATA, S_CRC };

static uint32_t crc32_byte(uint32_t crc, uint8_t b)
{
    crc ^= b;
    for (int i = 0; i < 8; i++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    return crc;
}

static void reset_frame(vecrx_t *r)
{
    r->state = S_SYNC0;
    r->idx   = 0;
}

void vecrx_init(vecrx_t *r)
{
    memset(r, 0, sizeof *r);
    reset_frame(r);
}

int vecrx_busy(const vecrx_t *r)
{
    return r->state != S_SYNC0;
}

void vecrx_set_window(vecrx_t *r, uint16_t *hi_v, uint8_t *lo_v, uint16_t *hi_i, uint8_t *lo_i)
{
    r->hi_v = hi_v;
    r->lo_v = lo_v;
    r->hi_i = hi_i;
    r->lo_i = lo_i;
}

static void start_data(vecrx_t *r)
{
    r->got = 0;
    r->idx = 0;
    r->crc = 0xFFFFFFFFu;
    r->sum_v = r->sum_i = 0;
    r->min_v = r->min_i = 0xFFFFu;
    r->max_v = r->max_i = 0;
    cic_init(&r->cic_v);
    cic_init(&r->cic_i);
    r->n_out_max = 60000u / r->f0; /* 4 ciclos a 15 kS/s: 1000 (60 Hz) o 1200 (50 Hz) */
    r->n_out = 0;
    r->crc_s = 0xFFFFFFFFu;
    r->sum_sv = r->sum_si = 0;
    r->first_sv = r->first_si = r->last_sv = r->last_si = 0;
    if (r->lo_v) memset(r->lo_v, 0, EST_LO_BYTES(r->n_out_max));
    if (r->lo_i) memset(r->lo_i, 0, EST_LO_BYTES(r->n_out_max));
    r->state = S_DATA;
}

static void crc_word(uint32_t *crc, uint32_t w)
{
    for (int k = 0; k < 4; k++) *crc = crc32_byte(*crc, (uint8_t)(w >> (8 * k)));
}

int vecrx_feed(vecrx_t *r, uint8_t c, uint32_t now_ms)
{
    r->t_last = now_ms;
    switch (r->state) {
    case S_SYNC0:
        if (c == 0x55) r->state = S_SYNC1;
        return VECRX_BUSY;
    case S_SYNC1:
        if (c == 0x56) {
            r->state = S_HDR;
            r->idx = 0;
        } else {
            r->state = (c == 0x55) ? S_SYNC1 : S_SYNC0;
        }
        return VECRX_BUSY;
    case S_HDR:
        r->buf[r->idx++] = c;
        if (r->idx < 4) return VECRX_BUSY;
        r->n_in  = (uint16_t)(r->buf[0] | r->buf[1] << 8);
        r->f0    = r->buf[2];
        r->flags = r->buf[3];
        if (r->n_in == 0 || r->n_in > VECRX_N_MAX || (r->f0 != 50 && r->f0 != 60)) {
            reset_frame(r);
            return VECRX_HDR;
        }
        start_data(r);
        return VECRX_BUSY;
    case S_DATA: {
        r->crc = crc32_byte(r->crc, c);
        r->buf[r->idx++] = c;
        if (r->idx < 4) return VECRX_BUSY;
        r->idx = 0;
        uint16_t v = (uint16_t)(r->buf[0] | r->buf[1] << 8);
        uint16_t i = (uint16_t)(r->buf[2] | r->buf[3] << 8);
        r->sum_v += v;
        r->sum_i += i;
        if (v < r->min_v) r->min_v = v;
        if (v > r->max_v) r->max_v = v;
        if (i < r->min_i) r->min_i = i;
        if (i > r->max_i) r->max_i = i;

        int32_t sv, si;
        int ov = cic_push(&r->cic_v, v, &sv);
        int oi = cic_push(&r->cic_i, i, &si);
        if (ov && oi && r->n_out < r->n_out_max) {
            if (r->n_out == 0) {
                r->first_sv = sv;
                r->first_si = si;
            }
            r->last_sv = sv;
            r->last_si = si;
            if (r->hi_v) est_store(r->hi_v, r->lo_v, r->n_out, (uint32_t)sv);
            if (r->hi_i) est_store(r->hi_i, r->lo_i, r->n_out, (uint32_t)si);
            r->sum_sv += (uint32_t)sv;
            r->sum_si += (uint32_t)si;
            crc_word(&r->crc_s, (uint32_t)sv);
            crc_word(&r->crc_s, (uint32_t)si);
            r->n_out++;
        }
        if (++r->got >= r->n_in) {
            r->state = S_CRC;
            r->idx = 0;
        }
        return VECRX_BUSY;
    }
    case S_CRC:
        r->buf[r->idx++] = c;
        if (r->idx < 4) return VECRX_BUSY;
        r->crc_rx   = (uint32_t)r->buf[0] | (uint32_t)r->buf[1] << 8 | (uint32_t)r->buf[2] << 16 |
                      (uint32_t)r->buf[3] << 24;
        r->crc_calc = ~r->crc;
        r->crc_s    = ~r->crc_s; /* CRC final de las salidas del CIC */
        reset_frame(r);
        return r->crc_calc == r->crc_rx ? VECRX_OK : VECRX_CRC;
    }
    reset_frame(r);
    return VECRX_BUSY;
}

int vecrx_poll(vecrx_t *r, uint32_t now_ms)
{
    if (r->state != S_SYNC0 && (int32_t)(now_ms - r->t_last) > (int32_t)VECRX_TIMEOUT_MS) {
        reset_frame(r);
        return VECRX_TIMEOUT;
    }
    return VECRX_BUSY;
}
