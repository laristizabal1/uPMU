#include "estimator.h"
#include <math.h>
#ifdef EST_PROFILE /* perfil por etapa con el contador de ciclos del DWT (solo en builds de medicion) */
#include "stm32f3xx.h"
uint32_t est_prof[8];
#define PROF_T0() uint32_t _t = DWT->CYCCNT
#define PROF(i) do { uint32_t _n = DWT->CYCCNT; est_prof[i] += _n - _t; _t = _n; } while (0)
#else
#define PROF_T0()
#define PROF(i)
#endif

#ifdef EST_DOUBLE
#define SIN  sin
#define COS  cos
#define ATAN2 atan2
#define HYPOT hypot
#define SQRT sqrt
#else
#define SIN  sinf
#define COS  cosf
#define ATAN2 atan2f
#define HYPOT hypotf
#define SQRT sqrtf
#endif

#define TWO_PI ((est_real)6.283185307179586476925287)
#define K0   4u /* 4 ciclos en la ventana: el pico de la fundamental cae en el bin 4 */
#define NB   5u /* bines a calcular: k0-2 .. k0+2 = vecinos de los 3 candidatos k0-1 .. k0+1 (f0 +- 22 Hz) */
#define K_LO (K0 - 2u)
#define K_HI (K0 + 2u)

/* Las senales (ventana Hann, portadora de la DFT, portadora del ajuste) se generan por rotacion compleja
 * (4 productos por muestra) y se reanclan cada SEED_M muestras con sin/cos exactos: sin el reanclaje el error
 * de fase crece ~ n * 6e-8 rad en float32 (6e-5 rad en 1000 muestras); con M = 48 queda < 3e-6 rad. Reemplaza
 * ~60 000 llamadas a sinf/cosf (~360 ciclos c/u en newlib) por ~2 000 por ventana. */
/* Ventana circular: la muestra n (0..N-1) de la ventana esta en el indice (start + n) mod len de (hi, lo). */
#define WRAP(i, len) ((i) >= (len) ? (i) - (len) : (i))
#define NEXTI(i, len) (((i) + 1u == (len)) ? 0u : (i) + 1u)

#define SEED_M   48u
#define SEED_MAX (EST_N_MAX / SEED_M + 1u)

/* Tablas que dependen solo de N (ventana Hann y portadora de la DFT): se construyen una vez por N. */
static uint32_t tab_n;
static est_real w_c[SEED_MAX], w_s[SEED_MAX], d_c[SEED_MAX], d_s[SEED_MAX];
static est_real w_cr, w_sr, d_cr, d_sr;

static void build_tables(uint32_t N)
{
    if (tab_n == N) return;
    uint32_t nb = (N + SEED_M - 1u) / SEED_M;
    for (uint32_t j = 0; j < nb; j++) {
        uint32_t n = j * SEED_M;
        est_real a = TWO_PI * (est_real)(n + 1u) / (est_real)(N + 1u); /* Hann de ref: np.hanning(N + 2)[1:-1] */
        w_c[j] = COS(a);
        w_s[j] = SIN(a);
        est_real b = TWO_PI * (est_real)n / (est_real)N; /* portadora de la DFT: bines enteros 2 pi k n / N */
        d_c[j] = COS(b);
        d_s[j] = SIN(b);
    }
    w_cr = COS(TWO_PI / (est_real)(N + 1u));
    w_sr = SIN(TWO_PI / (est_real)(N + 1u));
    d_cr = COS(TWO_PI / (est_real)N);
    d_sr = SIN(TWO_PI / (est_real)N);
    tab_n = N;
}

/* |X[k]| de (y - media) * w para k = K_LO .. K_HI = 2 .. 6 (DFT directa). Los cos/sin(2 pi k n / N) salen de la
 * recurrencia de Chebyshev c_{k+1} = 2 c_1 c_k - c_{k-1} desenrollada a mano con acumuladores escalares (el
 * mismo codigo con arreglos y bucles costaba ~310 ciclos/muestra). Solo valido para K0 = 4. */
static void dft_bins(const uint16_t *hi, const uint8_t *lo, uint32_t len, uint32_t start, uint32_t N,
                     est_real mean, est_real *mag)
{
    est_real r2 = 0, r3 = 0, r4 = 0, r5 = 0, r6 = 0, i2 = 0, i3 = 0, i4 = 0, i5 = 0, i6 = 0;
    const est_real wcr = w_cr, wsr = w_sr, dcr = d_cr, dsr = d_sr;
    for (uint32_t blk = 0, n0 = 0; n0 < N; blk++, n0 += SEED_M) {
        est_real wc = w_c[blk], ws = w_s[blk], c1 = d_c[blk], s1 = d_s[blk];
        uint32_t n1 = n0 + SEED_M < N ? n0 + SEED_M : N;
        uint32_t idx = start + n0;
        idx = WRAP(idx, len);
        for (uint32_t n = n0; n < n1; n++, idx = NEXTI(idx, len)) {
            const est_real yw = ((est_real)est_load(hi, lo, idx) - mean) * ((est_real)0.5 - (est_real)0.5 * wc);
            const est_real c2 = 2 * c1;
            const est_real cc2 = c2 * c1 - 1, ss2 = c2 * s1;
            const est_real cc3 = c2 * cc2 - c1, ss3 = c2 * ss2 - s1;
            const est_real cc4 = c2 * cc3 - cc2, ss4 = c2 * ss3 - ss2;
            const est_real cc5 = c2 * cc4 - cc3, ss5 = c2 * ss4 - ss3;
            const est_real cc6 = c2 * cc5 - cc4, ss6 = c2 * ss5 - ss4;
            r2 += yw * cc2;  i2 += yw * ss2;
            r3 += yw * cc3;  i3 += yw * ss3;
            r4 += yw * cc4;  i4 += yw * ss4;
            r5 += yw * cc5;  i5 += yw * ss5;
            r6 += yw * cc6;  i6 += yw * ss6;
            est_real t = wc * wcr - ws * wsr;
            ws = ws * wcr + wc * wsr;
            wc = t;
            t = c1 * dcr - s1 * dsr;
            s1 = s1 * dcr + c1 * dsr;
            c1 = t;
        }
    }
    mag[0] = HYPOT(r2, i2);
    mag[1] = HYPOT(r3, i3);
    mag[2] = HYPOT(r4, i4);
    mag[3] = HYPOT(r5, i5);
    mag[4] = HYPOT(r6, i6);
}

/* Resuelve el sistema 3x3 M x = b (eliminacion gaussiana con pivoteo parcial). */
static int solve3(est_real M[3][3], est_real b[3], est_real x[3])
{
    for (int i = 0; i < 3; i++) {
        int p = i;
        for (int r = i + 1; r < 3; r++)
            if (fabsf((float)M[r][i]) > fabsf((float)M[p][i])) p = r;
        if (M[p][i] == 0) return -1;
        if (p != i) {
            for (int c = 0; c < 3; c++) { est_real t = M[i][c]; M[i][c] = M[p][c]; M[p][c] = t; }
            est_real t = b[i]; b[i] = b[p]; b[p] = t;
        }
        for (int r = i + 1; r < 3; r++) {
            est_real f = M[r][i] / M[i][i];
            for (int c = i; c < 3; c++) M[r][c] -= f * M[i][c];
            b[r] -= f * b[i];
        }
    }
    for (int i = 2; i >= 0; i--) {
        est_real s = b[i];
        for (int c = i + 1; c < 3; c++) s -= M[i][c] * x[c];
        x[i] = s / M[i][i];
    }
    return 0;
}

/* Semillas de la portadora del ajuste para la frecuencia f: cos/sin(2 pi f tau) en n = j * SEED_M, y el giro
 * por muestra (2 pi f / fs). tau = (n - (N-1)/2) / fs. Se calculan una vez por f y sirven al ajuste y al
 * residuo de esa iteracion. */
typedef struct {
    est_real c[SEED_MAX], s[SEED_MAX];
    est_real cr, sr;
} carrier_t;

static void carrier_init(carrier_t *k, uint32_t N, est_real fs, est_real f)
{
    est_real half = (est_real)0.5 * (est_real)(N - 1u);
    uint32_t nb = (N + SEED_M - 1u) / SEED_M;
    for (uint32_t j = 0; j < nb; j++) {
        est_real th = TWO_PI * f * (((est_real)(j * SEED_M)) - half) / fs;
        k->c[j] = COS(th);
        k->s[j] = SIN(th);
    }
    k->cr = COS(TWO_PI * f / fs);
    k->sr = SIN(TWO_PI * f / fs);
}

/* Recorridos de la ventana a la frecuencia de `k` (portadora y ventana Hann por rotacion, reanclados por bloque).
 * Los acumuladores son locales (registros de la FPU): con acumuladores en memoria cada muestra costaba ~160 ciclos.
 *  - fit_sweep:   sistema normal de y ~ a cos + b sin + c con peso w^2 (matriz simetrica M y vector b);
 *  - resid_sweep: num = sum w^2 dr r y den = sum w^2 dr^2 del paso de Gauss-Newton. */
static void fit_sweep(const uint16_t *hi, const uint8_t *lo, uint32_t len, uint32_t start, uint32_t N,
                      est_real mean, const carrier_t *k,
                      est_real M[3][3], est_real b[3])
{
    est_real m00 = 0, m01 = 0, m02 = 0, m11 = 0, m12 = 0, m22 = 0, b0 = 0, b1 = 0, b2 = 0;
    const est_real cr = k->cr, sr = k->sr, wcr = w_cr, wsr = w_sr;
    for (uint32_t blk = 0, n0 = 0; n0 < N; blk++, n0 += SEED_M) {
        est_real c = k->c[blk], s = k->s[blk], wc = w_c[blk], ws = w_s[blk];
        uint32_t n1 = n0 + SEED_M < N ? n0 + SEED_M : N;
        uint32_t idx = start + n0;
        idx = WRAP(idx, len);
        for (uint32_t n = n0; n < n1; n++, idx = NEXTI(idx, len)) {
            est_real w = (est_real)0.5 - (est_real)0.5 * wc, w2 = w * w;
            est_real yy = (est_real)est_load(hi, lo, idx) - mean;
            est_real wcc = w2 * c, wss = w2 * s;
            m00 += wcc * c;  m01 += wcc * s;  m02 += wcc;
            m11 += wss * s;  m12 += wss;      m22 += w2;
            b0 += wcc * yy;  b1 += wss * yy;  b2 += w2 * yy;
            est_real t = c * cr - s * sr;
            s = s * cr + c * sr;
            c = t;
            t = wc * wcr - ws * wsr;
            ws = ws * wcr + wc * wsr;
            wc = t;
        }
    }
    M[0][0] = m00; M[0][1] = M[1][0] = m01; M[0][2] = M[2][0] = m02;
    M[1][1] = m11; M[1][2] = M[2][1] = m12; M[2][2] = m22;
    b[0] = b0; b[1] = b1; b[2] = b2;
}

static void resid_sweep(const uint16_t *hi, const uint8_t *lo, uint32_t len, uint32_t start, uint32_t N,
                        est_real fs, est_real mean,
                        const carrier_t *k, const est_real sol[3], est_real *num, est_real *den)
{
    est_real nu = 0, de = 0;
    const est_real cr = k->cr, sr = k->sr, wcr = w_cr, wsr = w_sr;
    const est_real a = sol[0], bb = sol[1], cc0 = sol[2];
    const est_real half = (est_real)0.5 * (est_real)(N - 1u), k2 = TWO_PI / fs;
    for (uint32_t blk = 0, n0 = 0; n0 < N; blk++, n0 += SEED_M) {
        est_real c = k->c[blk], s = k->s[blk], wc = w_c[blk], ws = w_s[blk];
        uint32_t n1 = n0 + SEED_M < N ? n0 + SEED_M : N;
        uint32_t idx = start + n0;
        idx = WRAP(idx, len);
        for (uint32_t n = n0; n < n1; n++, idx = NEXTI(idx, len)) {
            est_real w = (est_real)0.5 - (est_real)0.5 * wc, w2 = w * w;
            est_real yy = (est_real)est_load(hi, lo, idx) - mean;
            est_real r = yy - (a * c + bb * s + cc0);
            est_real dr = k2 * ((est_real)n - half) * (bb * c - a * s);
            est_real w2dr = w2 * dr;
            nu += w2dr * r;
            de += w2dr * dr;
            est_real t = c * cr - s * sr;
            s = s * cr + c * sr;
            c = t;
            t = wc * wcr - ws * wsr;
            ws = ws * wcr + wc * wsr;
            wc = t;
        }
    }
    *num = nu;
    *den = de;
}

static int fit(const uint16_t *hi, const uint8_t *lo, uint32_t len, uint32_t start, uint32_t N, est_real mean,
               const carrier_t *k, est_real sol[3])
{
    est_real M[3][3], b[3];
    fit_sweep(hi, lo, len, start, N, mean, k, M, b);
    return solve3(M, b, sol);
}

int est_run(const uint16_t *hi, const uint8_t *lo, uint32_t len, uint32_t start, uint32_t N, est_real fs,
            uint32_t k0, est_t *out)
{
    if (N < 16u || N > EST_N_MAX || len < N || start >= len || k0 != K0 || fs <= 0) return -1;
    PROF_T0();
    build_tables(N);
    PROF(0);

    uint32_t sum = 0; /* entero exacto (1200 * 262143 = 3,1e8 cabe en 32 bits) */
    for (uint32_t n = 0, idx = start; n < N; n++, idx = NEXTI(idx, len)) sum += est_load(hi, lo, idx);
    est_real mean = (est_real)sum / (est_real)N;
    PROF(1);

    /* IpDFT: pico en k0-1 .. k0+1 y vecino mayor (formula de Grandke para Hann); ref busca en k0-2 .. k0+2 */
    est_real X[NB];
    dft_bins(hi, lo, len, start, N, mean, X); /* X[j] es el bin K_LO + j */
    PROF(2);
    uint32_t jb = 1;                       /* candidatos: bines k0-1 .. k0+1 -> j = 1 .. 3 */
    for (uint32_t j = 2; j <= 3; j++)
        if (X[j] > X[jb]) jb = j;
    int up = X[jb + 1] >= X[jb - 1];
    est_real a = (up ? X[jb + 1] : X[jb - 1]) / X[jb];
    est_real d = (2 * a - 1) / (a + 1);
    est_real delta = up ? d : -d;
    est_real f = ((est_real)(K_LO + jb) + delta) * fs / (est_real)N;

    /* Minimos cuadrados + Gauss-Newton sobre f */
    carrier_t k;
    est_real sol[3];
    PROF(3);
    carrier_init(&k, N, fs, f);
    PROF(4);
    if (fit(hi, lo, len, start, N, mean, &k, sol) != 0) return -1;
    PROF(5);
    for (uint32_t it = 0; it < EST_ITER; it++) {
        est_real num, den;
        resid_sweep(hi, lo, len, start, N, fs, mean, &k, sol, &num, &den);
        PROF(6);
        if (den == 0) break;
        f += num / den;
        carrier_init(&k, N, fs, f);
        PROF(4);
        if (fit(hi, lo, len, start, N, mean, &k, sol) != 0) return -1;
        PROF(5);
    }
    out->f_hz    = f;
    out->mag_rms = HYPOT(sol[0], sol[1]) / SQRT((est_real)2);
    out->ang_rad = ATAN2(-sol[1], sol[0]); /* c = a - jb */
    return 0;
}
