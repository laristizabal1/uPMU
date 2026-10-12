"""Cadena completa: red -> sensor -> burden -> filtro RC -> ADC 12 bit @60 kS/s
-> CIC3 (R=4) -> IpDFT (Hann) + ajuste por minimos cuadrados -> fasor -> TVE.

Alcance: analogico + ADC + estimador.  Fuera de alcance: error de tiempo del PPS
(se asume que cada muestra tiene su sello de tiempo correcto) y error de fase de
los sensores reales (se modela como desfase constante desconocido y se calibra).
"""
import numpy as np
import params as P

rng = np.random.default_rng(20261008)

REFINE = True
NOISE_LSB = 1.5   # ruido rms del ADC (referido a la entrada), valor conservador
H_CIC = np.convolve(np.convolve(np.ones(4), np.ones(4)), np.ones(4)) / 64.0
CIC_DELAY = (len(H_CIC) - 1) / 2  # 4.5 muestras @60 kHz


def cic_gain(f):
    x = np.pi * f / P.FS
    return (np.sin(P.DECIM * x) / (P.DECIM * np.sin(x))) ** 3


class Chain:
    """Un par de canales (V, I) con valores reales (con tolerancia)."""

    def __init__(self, grid, tol=True, sensor_phase=True):
        g = P.GRIDS[grid]
        self.grid, self.f0 = grid, g["f0"]
        t = (lambda pct: 1 + (rng.uniform(-pct, pct) if tol else 0.0))
        self.Rp = g["Rp"] * t(0.01)
        self.RbV, self.RfV = P.RB_V * t(0.01), P.RF_V * t(0.01)
        self.RbI, self.RfI = P.RB_I * t(0.01), P.RF_I * t(0.01)
        self.CV, self.CI = P.C_F * t(0.05), P.C_F * t(0.05)
        self.ct_ratio = P.CT_RATIO * t(0.01)
        # desfase constante de sensores: ZMPT101B ~ +-0.3 deg, SCT013 ~ +-1 deg (supuestos)
        self.phV = np.radians(rng.uniform(-0.3, 0.3)) if sensor_phase else 0.0
        self.phI = np.radians(rng.uniform(-1.0, 1.0)) if sensor_phase else 0.0
        self.grid_Rp_nom = g["Rp"]
        self.kappa_v = 1.0 + 0j
        self.kappa_i = 1.0 + 0j

    # --- funciones de transferencia reales (V red -> V en el nodo ADC) -------------
    def Hv(self, f):
        w = 2 * np.pi * f
        return (self.RbV / self.Rp) * np.exp(1j * self.phV) / (1 + 1j * w * self.CV * (self.RbV + self.RfV))

    def Hi(self, f):   # A primario -> V nodo ADC
        w = 2 * np.pi * f
        return (self.RbI / self.ct_ratio) * np.exp(1j * self.phI) / (1 + 1j * w * self.CI * (self.RbI + self.RfI))

    # --- modelo NOMINAL usado por el firmware ----------------------------------
    def Hv_nom(self, f):
        w = 2 * np.pi * f
        return (P.RB_V / self.grid_Rp_nom) / (1 + 1j * w * P.C_F * (P.RB_V + P.RF_V))

    def Hi_nom(self, f):
        w = 2 * np.pi * f
        return (P.RB_I / P.CT_RATIO) / (1 + 1j * w * P.C_F * (P.RB_I + P.RF_I))


def acquire(chain, f, Xv, Xi, t0, n_dec_samples, noise=True, harmonics=()):
    """Devuelve las dos secuencias decimadas (codigos ADC) y sus sellos de tiempo.
    Xv, Xi: fasores rms complejos referidos a t=0 (modulo en V y A)."""
    n_in = n_dec_samples * P.DECIM + len(H_CIC) + 8
    t = t0 + np.arange(n_in) / P.FS
    codes = []
    for H, X, extra in ((chain.Hv, Xv, 0), (chain.Hi, Xi, 1)):
        y = np.real(np.sqrt(2) * X * H(f) * np.exp(2j * np.pi * f * t))
        for (k, rel) in harmonics:   # armonicos relativos a la fundamental
            y += np.real(np.sqrt(2) * X * rel * H(k * f) * np.exp(2j * np.pi * k * f * t))
        v = P.VCM + y + (rng.normal(0, 0.002) if noise else 0.0)  # offset ~2 mV
        c = v / P.LSB + (rng.normal(0, NOISE_LSB, n_in) if noise else 0.0)
        c = np.clip(np.round(c), 0, 2 ** P.NBITS - 1)
        codes.append(c)
    out_t, out = None, []
    for c in codes:
        yf = np.convolve(c, H_CIC)
        ks = np.arange(len(H_CIC) - 1, len(yf) - len(H_CIC), P.DECIM)[:n_dec_samples]
        out.append(yf[ks] * P.LSB)         # volts (con offset VCM)
        out_t = t0 + (ks - CIC_DELAY) / P.FS
    return out_t, out[0], out[1]


def ipdft_ls(t, y, f0, cycles=P.CYCLES):
    """IpDFT con Hann para frecuencia + LS ponderado (Hann) para fasor en el centro."""
    N = len(y)
    fs = 1.0 / (t[1] - t[0])
    w = np.hanning(N + 2)[1:-1]
    X = np.abs(np.fft.rfft((y - y.mean()) * w))
    k0 = int(round(f0 * N / fs))
    k = k0 - 2 + int(np.argmax(X[k0 - 2:k0 + 3]))
    nb = k + 1 if X[k + 1] >= X[k - 1] else k - 1
    a = X[nb] / X[k]
    d = (2 * a - 1) / (a + 1)
    # formula de Grandke para Hann: delta = (2a-1)/(a+1) hacia el lado del vecino mayor
    delta = d if nb > k else -d
    f_est = (k + delta) * fs / N
    tc = t.mean()
    tau = t - tc

    def fit(f):
        A = np.column_stack([np.cos(2 * np.pi * f * tau), np.sin(2 * np.pi * f * tau), np.ones(N)])
        sol, *_ = np.linalg.lstsq(A * w[:, None], y * w, rcond=None)
        return sol

    sol = fit(f_est)
    if REFINE:   # Gauss-Newton sobre f: elimina el sesgo por imagen de IpDFT (~15 mHz con 4 ciclos)
        for _ in range(4):
            a_, b_, c_ = sol
            wt = 2 * np.pi * f_est * tau
            r = y - (a_ * np.cos(wt) + b_ * np.sin(wt) + c_)
            dr = 2 * np.pi * tau * (-a_ * np.sin(wt) + b_ * np.cos(wt))   # d(modelo)/df
            df = np.sum(w * w * dr * r) / np.sum(w * w * dr * dr)
            f_est += df
            sol = fit(f_est)
    c = sol[0] - 1j * sol[1]                    # y = Re{c e^{j w tau}}  (c = R e^{j theta})
    return f_est, c / np.sqrt(2), tc            # fasor rms en el centro de la ventana


def measure(chain, f, Xv, Xi, t0, noise=True, harmonics=()):
    n = int(round(P.CYCLES / chain.f0 * P.FS / P.DECIM))
    t, yv, yi = acquire(chain, f, Xv, Xi, t0, n, noise, harmonics)
    fv, cv, tc = ipdft_ls(t, yv, chain.f0)
    fi, ci, _ = ipdft_ls(t, yi, chain.f0)
    f_est = 0.5 * (fv + fi)
    # fasor rms -> fisico:  / (H_nominal * H_cic)   [el retardo del CIC ya esta en los sellos]
    xv = cv / (chain.Hv_nom(f_est) * cic_gain(f_est))
    xi = ci / (chain.Hi_nom(f_est) * cic_gain(f_est))
    return f_est, xv * chain.kappa_v, xi * chain.kappa_i, tc


def true_phasor(X, f, tc):
    return X * np.exp(2j * np.pi * f * tc)


def tve(est, ref):
    return abs(est - ref) / abs(ref) * 100.0


def calibrate(chain, Xv, Xi):
    """Calibracion de 1 punto (nominal) con referencia: kappa = X_ref / X_medido (sin ruido)."""
    chain.kappa_v = chain.kappa_i = 1.0 + 0j
    t0 = 0.2
    f_est, xv, xi, tc = measure(chain, chain.f0, Xv, Xi, t0, noise=False)
    chain.kappa_v = true_phasor(Xv, chain.f0, tc) / xv
    chain.kappa_i = true_phasor(Xi, chain.f0, tc) / xi


def scenarios(grid):
    g = P.GRIDS[grid]
    f0 = g["f0"]
    L = [("nominal", f0, 1.0, 1.0), ("V 80 %, I 10 %", f0, 0.8, 0.10), ("V 120 %, I 200 %", f0, 1.2, 2.0),
         ("f0 - 2 Hz", f0 - 2, 1.0, 1.0), ("f0 + 2 Hz", f0 + 2, 1.0, 1.0),
         ("f0 - 5 Hz", f0 - 5, 1.0, 1.0), ("f0 + 5 Hz", f0 + 5, 1.0, 1.0)]
    return L


def run(grid, ndraws=200):
    g = P.GRIDS[grid]
    res = {}
    uncal = []
    for _ in range(ndraws):
        ch = Chain(grid)
        Xv0 = g["Vrms"] * np.exp(1j * np.radians(20.0))
        Xi0 = g["In_rms"] * np.exp(1j * np.radians(20.0 - 30.0))
        # sin calibrar (nominal)
        f_e, xv, xi, tc = measure(ch, g["f0"], Xv0, Xi0, 0.2)
        uncal.append((tve(xv, true_phasor(Xv0, g["f0"], tc)), tve(xi, true_phasor(Xi0, g["f0"], tc))))
        calibrate(ch, Xv0, Xi0)
        for (name, f, vs, is_) in scenarios(grid):
            Xv = vs * Xv0
            Xi = is_ * Xi0
            t0 = rng.uniform(0.0, 1.0 / f)
            f_e, xv, xi, tc = measure(ch, f, Xv, Xi, t0)
            tv, ti = tve(xv, true_phasor(Xv, f, tc)), tve(xi, true_phasor(Xi, f, tc))
            dphi = np.degrees(np.angle(xv / xi)) - np.degrees(np.angle(true_phasor(Xv, f, tc) / true_phasor(Xi, f, tc)))
            res.setdefault(name, []).append((tv, ti, abs(dphi), abs(f_e - f) * 1e3,
                                            abs(abs(xv) / abs(Xv) - 1) * 100, abs(abs(xi) / abs(Xi) - 1) * 100))
    return res, np.array(uncal)


if __name__ == "__main__":
    import json
    out = {}
    for grid in P.GRIDS:
        res, uncal = run(grid)
        print(f"\n=== {grid} ({P.GRIDS[grid]['f0']:g} Hz, {P.GRIDS[grid]['Vrms']:g} V) - 200 combinaciones de tolerancia ===")
        print("Sin calibrar (nominal): TVE_V p95 = %.2f %%, TVE_I p95 = %.2f %%" % (
            np.percentile(uncal[:, 0], 95), np.percentile(uncal[:, 1], 95)))
        print("Calibrado a 1 punto.  Valores = percentil 95 sobre las 200 combinaciones")
        print("%-20s %8s %8s %12s %10s" % ("escenario", "TVE_V %", "TVE_I %", "dFase V-I °", "df mHz"))
        out[grid] = {}
        for name, rows in res.items():
            a = np.array(rows)
            p = np.percentile(a, 95, axis=0)
            mx = a.max(axis=0)
            print("%-20s %8.3f %8.3f %12.4f %10.2f   (max TVE_V=%.3f TVE_I=%.3f)" % (name, p[0], p[1], p[2], p[3], mx[0], mx[1]))
            out[grid][name] = dict(p95=p.tolist(), max=mx.tolist())
        out[grid]["uncal_p95"] = np.percentile(uncal, 95, axis=0).tolist()
    json.dump(out, open("results_chain.json", "w"), indent=1)
