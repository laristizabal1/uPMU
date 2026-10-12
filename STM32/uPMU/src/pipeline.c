#include "pipeline.h"
#include "estimator.h"
#include <string.h>

int pipe_init(pipe_t *p, uint32_t f0, uint16_t *hi_v, uint8_t *lo_v, uint16_t *hi_i, uint8_t *lo_i)
{
    if (f0 != 50 && f0 != 60) return -1;
    memset(p, 0, sizeof *p);
    p->n      = 60000u / f0;        /* 4 ciclos a 15 kS/s */
    p->period = p->n / 2u;          /* 500 -> 30 fps (60 Hz); 600 -> 25 fps (50 Hz) */
    p->len    = p->n + PIPE_SLACK;
    p->hi_v = hi_v; p->lo_v = lo_v; p->hi_i = hi_i; p->lo_i = lo_i;
    memset(lo_v, 0, (p->len + 3u) / 4u);
    memset(lo_i, 0, (p->len + 3u) / 4u);
    cic_init(&p->cic_v);
    cic_init(&p->cic_i);
    p->next_due = p->n;             /* primer reporte cuando la ventana se llena */
    return 0;
}

void pipe_push(pipe_t *p, uint32_t v, uint32_t i)
{
    int32_t sv, si;
    p->n_in++;
    int ov = cic_push(&p->cic_v, v, &sv);
    int oi = cic_push(&p->cic_i, i, &si);
    if (!(ov && oi)) return;

    est_store(p->hi_v, p->lo_v, p->wp, (uint32_t)sv);
    est_store(p->hi_i, p->lo_i, p->wp, (uint32_t)si);
    p->wp = (p->wp + 1u == p->len) ? 0u : p->wp + 1u;
    p->n_out++;

    if (p->n_out == p->next_due) {
        uint32_t start = p->wp + p->len - p->n; /* las n salidas mas recientes */
        if (start >= p->len) start -= p->len;
        p->rep_start = start;
        p->rep_n_out = p->n_out;
        p->rep_seq++;
        p->next_due += p->period;
    }
}

int pipe_take(pipe_t *p, uint32_t *seen, uint32_t *start, uint32_t *n_out_at, uint32_t *skipped)
{
    uint32_t s1, s2, st, no;
    do { /* la ISR puede disparar entre lecturas: se repite hasta tener una instantanea coherente */
        s1 = p->rep_seq;
        st = p->rep_start;
        no = p->rep_n_out;
        s2 = p->rep_seq;
    } while (s1 != s2);
    if (s1 == *seen) return 0;
    *skipped = s1 - *seen - 1u;
    *seen = s1;
    *start = st;
    *n_out_at = no;
    return 1;
}

int pipe_window_valid(const pipe_t *p, uint32_t n_out_at)
{
    return (uint32_t)(p->n_out - n_out_at) <= PIPE_SLACK;
}
