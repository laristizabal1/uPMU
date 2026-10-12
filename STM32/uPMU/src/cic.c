#include "cic.h"
#include <string.h>

void cic_init(cic_t *c)
{
    memset(c, 0, sizeof *c);
}

int cic_push(cic_t *c, uint32_t x, int32_t *y)
{
    uint32_t idx = c->n++;
    c->i1 += x; /* uint32_t: desbordamiento modular definido */
    c->i2 += c->i1;
    c->i3 += c->i2;
    if ((idx & (CIC_R - 1u)) != CIC_PHASE) return 0;

    uint32_t z = c->i3;
    uint32_t a = z - c->c1;
    c->c1 = z;
    uint32_t b = a - c->c2;
    c->c2 = a;
    uint32_t w = b - c->c3;
    c->c3 = b;
    if (idx < CIC_FIRST) return 0; /* transitorio: todavia hay ceros de la ventana inicial */
    *y = (int32_t)w;
    return 1;
}
