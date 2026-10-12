# -*- coding: utf-8 -*-
"""Regenera los netlists, los corre en LTspice (modo batch -b), analiza y grafica.

    python run_ltspice.py            # todo; deja results_ltspice.txt y los PNG
    python run_ltspice.py --no-run   # solo reanaliza los .raw que ya existen

Busca LTspice.exe en las rutas usuales de Windows o en la variable $LTSPICE.
"""
import os
import runpy
import subprocess
import sys
from pathlib import Path

import numpy as np

import ltspice_raw as LR
import params as P

# Umbrales del enunciado para marcar una diferencia como relevante.
TOL_MAG = 0.1      # %
TOL_PH = 0.05      # grados

from rutas import NETLISTS, FIGURAS, RESULTADOS

HERE = NETLISTS
CANDIDATES = [
    r"C:\Program Files\ADI\LTspice\LTspice.exe",
    r"C:\Program Files\LTC\LTspiceXVII\XVIIx64.exe",
    r"C:\Program Files (x86)\LTC\LTspiceIV\scad3.exe",
]
DO_RUN = "--no-run" not in sys.argv
OUT = []          # lineas del informe


def say(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s)


def find_ltspice():
    for p in [os.environ.get("LTSPICE")] + CANDIDATES:
        if p and Path(p).exists():
            return p
    sys.exit("No encuentro LTspice.exe.  Define la variable de entorno LTSPICE.")


LT = find_ltspice() if (DO_RUN and __name__ == "__main__") else None

if DO_RUN and __name__ == "__main__":      # netlists siempre al dia
    runpy.run_path(str(Path(__file__).parent / "make_netlists.py"), run_name="__main__")
    runpy.run_path(str(Path(__file__).parent / "make_asc.py"), run_name="__main__")


def flag(dmag_pct, dph_deg):
    """Marca si una diferencia supera los umbrales del enunciado."""
    out = []
    if abs(dmag_pct) > TOL_MAG:
        out.append("MODULO>%.1f%%" % TOL_MAG)
    if abs(dph_deg) > TOL_PH:
        out.append("FASE>%.2fdeg" % TOL_PH)
    return ("  <<< " + ", ".join(out)) if out else ""


def run(cir):
    """Corre un netlist en batch y devuelve el diccionario del .raw (o la lista
    de pasos si hay .step)."""
    raw = HERE / (cir[:-4] + ".raw")
    if DO_RUN:
        subprocess.run([LT, "-b", "-ascii", str(HERE / cir)],
                       capture_output=True, text=True)
    if not raw.exists():
        log = HERE / (cir[:-4] + ".log")
        sys.exit("LTspice fallo en %s\n%s" % (
            cir, log.read_text(errors="replace") if log.exists() else ""))
    return LR.read(raw)


from afe_model import h_exact, h_v, h_i, h_simple_v, h_simple_i


def at(d, node, f, fwant):
    """Valor complejo interpolado (en re/im) a la frecuencia fwant."""
    return (np.interp(fwant, f, d[node].real)
            + 1j * np.interp(fwant, f, d[node].imag))


# =========================================================================
say("=" * 74)
say("uPMU AFE en LTspice  (%s)" % (LT or "reanalisis sin correr"))
say("=" * 74)

# --- 1. AC por canal, un solo canal excitado ------------------------------
say("\n--- 1. AC (10 Hz..100 kHz), un canal excitado a la vez -------------")
acv = run("uPMU_AFE_ac_V.cir")[0]
aci = run("uPMU_AFE_ac_I.cir")[0]
fv = acv["frequency"].real
fi = aci["frequency"].real

say("%-6s %-26s %-26s %s" % ("f[Hz]", "canal V |H| / fase", "canal I |H| / fase", "fase V-I"))
for f0 in (50.0, 60.0):
    hv, hi = at(acv, "V(adcv)", fv, f0), at(aci, "V(adci)", fi, f0)
    dphi = np.degrees(np.angle(hv / hi))
    say("%-6g %.6e V/V %+8.4f  %.6e V/A %+8.4f  %+8.4f deg" % (
        f0, abs(hv), np.degrees(np.angle(hv)), abs(hi), np.degrees(np.angle(hi)), dphi))

say("\nLTspice vs modelo cerrado exacto de Python (mismo circuito, vcm = masa de")
say("alterna).  Umbrales: %.1f %% en modulo, %.2f deg en fase." % (TOL_MAG, TOL_PH))
for name, d, f, node, hf in (("V", acv, fv, "V(adcv)", h_v), ("I", aci, fi, "V(adci)", h_i)):
    for lo, hi in ((10, 100), (100, 1000), (1000, 5000), (5000, 100000)):
        m = (f >= lo) & (f <= hi)
        ref, sim = hf(f[m]), d[node][m]
        dm = abs(abs(sim) / abs(ref) - 1) * 100
        dp = abs(np.degrees(np.angle(sim / ref)))
        k = int(np.argmax(dp))
        say("  canal %s %6g-%6g Hz: max dMod %.4f %%, max dFase %.4f deg (a %.0f Hz)%s" % (
            name, lo, hi, dm.max(), dp.max(), f[m][k], flag(dm.max(), dp.max())))
say("  La diferencia que crece por encima de 5 kHz esta explicada: el modelo")
say("  cerrado no incluye la capacidad de juntura de los 1N4148 (Cjo 4 pF, ~2,5 pF")
say("  con 1,65 V de inversa, dos por nodo).  Suma ~5 pF al pin y mueve su polo de")
say("  23 MHz a 13 MHz: 0,02 deg a 5 kHz y 0,0003 deg a 60 Hz.")

say("\nLTspice vs la formula simple de simulate_chain.py (solo RC, CT ideal):")
for name, d, f, node, hf in (("V", acv, fv, "V(adcv)", h_simple_v),
                             ("I", aci, fi, "V(adci)", h_simple_i)):
    for f0 in (50.0, 60.0):
        sim = at(d, node, f, f0)
        ref = hf(f0)
        say("  canal %s a %g Hz: dMod = %+.4f %%, dFase = %+.4f deg" % (
            name, f0, 100 * (abs(sim) / abs(ref) - 1), np.degrees(np.angle(sim / ref))))

# --- 2. Efecto de modelar el CT (antes/despues) --------------------------
say("\n--- 2. Efecto de modelar el magnetizante del CT (antes/despues) ----")
acv0 = run("uPMU_AFE_ac_ideal_V.cir")[0]
aci0 = run("uPMU_AFE_ac_ideal_I.cir")[0]
f0v, f0i = acv0["frequency"].real, aci0["frequency"].real
say("%-6s %-22s %-22s %s" % ("f[Hz]", "fase V ideal->real", "fase I ideal->real", "fase V-I ideal->real"))
for f0 in (50.0, 60.0):
    pv0 = np.degrees(np.angle(at(acv0, "V(adcv)", f0v, f0)))
    pi0 = np.degrees(np.angle(at(aci0, "V(adci)", f0i, f0)))
    pv1 = np.degrees(np.angle(at(acv, "V(adcv)", fv, f0)))
    pi1 = np.degrees(np.angle(at(aci, "V(adci)", fi, f0)))
    say("%-6g %+7.4f -> %+7.4f     %+7.4f -> %+7.4f     %+7.4f -> %+7.4f deg" % (
        f0, pv0, pv1, pi0, pi1, pv0 - pi0, pv1 - pi1))
say("Sensibilidad de la fase V-I a la frecuencia (lo que NO quita calibrar en f0):")
for grid, f0 in (("Colombia", 60.0), ("Chile", 50.0)):
    d0 = np.degrees(np.angle(at(acv, "V(adcv)", fv, f0) / at(aci, "V(adci)", fi, f0)))
    for df in (-5.0, 5.0):
        d1 = np.degrees(np.angle(at(acv, "V(adcv)", fv, f0 + df)
                                 / at(aci, "V(adci)", fi, f0 + df)))
        say("  %-8s %g Hz %+g Hz: fase V-I %+.4f -> %+.4f deg (residuo %+.4f)" % (
            grid, f0, df, d0, d1, d1 - d0))
say("Fase absoluta por canal (importa para el fasor contra UTC):")
say("  (el firmware YA compensa el polo RC, asi que el residuo real es solo el")
say("   termino del CT: fase con CT real menos fase con CT ideal, referida a f0)")
for grid, f0 in (("Colombia", 60.0), ("Chile", 50.0)):
    for name, d, d0, f, fz, node in (("V", acv, acv0, fv, f0v, "V(adcv)"),
                                     ("I", aci, aci0, fi, f0i, "V(adci)")):
        # eps(f) = fase(CT real) - fase(CT ideal) = adelanto del transformador
        eps = lambda x: (np.degrees(np.angle(at(d, node, f, x)))
                         - np.degrees(np.angle(at(d0, node, fz, x))))
        e0, em, ep = eps(f0), eps(f0 - 5), eps(f0 + 5)
        say("  %-8s canal %s: fase cruda %+.4f deg | eps_CT %+.4f deg"
            " -> residuo tras calibrar en f0: %+.4f / %+.4f" % (
                grid, name, np.degrees(np.angle(at(d, node, f, f0))),
                e0, em - e0, ep - e0))

# --- 3. Atenuacion / anti-aliasing ---------------------------------------
say("\n--- 3. Atenuacion del canal V respecto a 60 Hz ---------------------")
h60 = abs(at(acv, "V(adcv)", fv, 60.0))
say("  " + ", ".join("%g Hz: %.1f dB" % (ff, 20 * np.log10(abs(at(acv, "V(adcv)", fv, ff)) / h60))
                     for ff in (1000, 4222, 7500, 15000, 30000, 100000)))
cic = lambda f: abs((np.sin(P.DECIM * np.pi * f / P.FS)
                     / (P.DECIM * np.sin(np.pi * f / P.FS))) ** 3)
# 15 k y 30 k son ceros exactos del CIC (R=4 a 60 kS/s): no son el peor caso.
say("  con el CIC3 (R=4) en cascada: " + ", ".join(
    "%g Hz: %.1f dB" % (ff, 20 * np.log10(abs(at(acv, "V(adcv)", fv, ff)) / h60 * cic(ff)))
    for ff in (7500, 11000, 22000, 37500, 52500)))
fg = np.linspace(7500, 60000, 4000)
tot = abs(np.interp(fg, fv, abs(acv["V(adcv)"]))) / h60 * cic(fg)
say("  peor rechazo entre 7,5 kHz y 60 kHz: %.1f dB a %.0f Hz"
    " (lo que alias a la banda de 15 kS/s)" % (20 * np.log10(tot.max()), fg[np.argmax(tot)]))

# --- 4. Transitorio: recorrido en el pin y margen ------------------------
say("\n--- 4. Transitorio: recorrido en el pin del ADC --------------------")
say("%-10s %-6s %-16s %-16s %s" % ("red", "carga", "V(adcv) min..max", "V(adci) min..max", "margen a 0/3,3 V"))
for grid in ("Colombia", "Chile"):
    suf = "" if grid == "Colombia" else "_" + grid
    for tag, cir in (("nom", "uPMU_AFE_tran%s.cir" % suf),
                     ("ovl", "uPMU_AFE_tran%s_ovl.cir" % suf)):
        d = run(cir)[0]
        t = d["time"]
        # La ventana ya viene asentada; se descarta un ciclo por si queda algo
        # del transitorio de continua del magnetizante.
        m = t >= t[0] + 1.0 / P.GRIDS[grid]["f0"]
        v, i = d["V(adcv)"][m], d["V(adci)"][m]
        lo = min(v.min(), i.min())
        hi = max(v.max(), i.max())
        say("%-10s %-6s %6.3f..%6.3f V  %6.3f..%6.3f V  %.3f V / %.3f V" % (
            grid, tag, v.min(), v.max(), i.min(), i.max(), lo, P.VDDA - hi))
        idmax = max(abs(d["I(D1v)"][m]).max(), abs(d["I(D2v)"][m]).max(),
                    abs(d["I(D1i)"][m]).max(), abs(d["I(D2i)"][m]).max())
        say("%22s corriente maxima en los 1N4148: %.2e A" % ("", idmax))
        # Comprobacion punto a punto en los instantes en que muestrea el ADC:
        # mas exigente que comparar picos, y es lo que de verdad ve el firmware.
        g, f0 = P.GRIDS[grid], P.GRIDS[grid]["f0"]
        vs_, is_ = (1.2, 2.0) if tag == "ovl" else (1.0, 1.0)
        ts = np.arange(t[m][0], t[m][-1], 1.0 / P.FS)
        w = 2 * np.pi * f0
        # Las fuentes del netlist son SIN(...), de ahi el imag(); la corriente
        # lleva el desfase phii = -30 grados que fija make_netlists.py.
        vm = P.VCM + np.imag(np.sqrt(2) * g["Vrms"] * vs_ * h_v(f0, grid=grid)
                             * np.exp(1j * w * ts))
        im = P.VCM + np.imag(np.sqrt(2) * g["In_rms"] * is_ * h_i(f0)
                             * np.exp(1j * (w * ts + np.radians(-30.0))))
        dv = np.max(abs(np.interp(ts, t[m], v) - vm))
        di = np.max(abs(np.interp(ts, t[m], i) - im))
        say("%22s vs modelo cerrado, muestra a muestra: dV %.3f mV, dI %.3f mV"
            " (1 LSB = %.3f mV)" % ("", 1e3 * dv, 1e3 * di, 1e3 * P.LSB))

# --- 5. Clamps en sobretension -------------------------------------------
say("\n--- 5. Clamps 1N4148 en sobretension (V 400 %, I 600 %) ------------")
d = run("uPMU_AFE_clamp.cir")[0]
t = d["time"]
m = t >= t[0] + 1.0 / 60.0
say("  V(adcv) %.3f..%.3f V, V(adci) %.3f..%.3f V" % (
    d["V(adcv)"][m].min(), d["V(adcv)"][m].max(),
    d["V(adci)"][m].min(), d["V(adci)"][m].max()))
for dn in ("I(D1v)", "I(D2v)", "I(D1i)", "I(D2i)"):
    say("  %-8s corriente maxima %.3e A" % (dn, abs(d[dn][m]).max()))

# --- 6. Muestreo del ADC: asentamiento a 12 bits -------------------------
say("\n--- 6. Red de muestreo del ADC: asentamiento a 12 bits -------------")
d = run("uPMU_AFE_adcsh.cir")[0]
t, g = d["time"], d["V(nsmp)"]
on = g > 0.5
ends = np.where(on[:-1] & ~on[1:])[0]        # ultimo indice de cada ventana
if len(ends) == 0:
    say("  (no se detectaron ventanas de muestreo)")
else:
    ev = abs(d["V(shv)"][ends] - d["V(adcv)"][ends])
    ei = abs(d["V(shi)"][ends] - d["V(adci)"][ends])
    say("  %d ventanas de %.2f us; error al cerrar el interruptor:" % (len(ends), 1e6 * P.T_SAMPLE))
    say("  canal V: max %.3e V = %.4f LSB | canal I: max %.3e V = %.4f LSB" % (
        ev.max(), ev.max() / P.LSB, ei.max(), ei.max() / P.LSB))
    tau = (P.RS_ADC + P.R_ADC) * P.C_ADC_SH
    say("  tau = (Rs+R_ADC)*C_SH = %.1f ns, 12 bits piden %.0f ns, hay %.2f us -> margen %.0fx" % (
        1e9 * tau, 1e9 * tau * np.log(2 ** (P.NBITS + 1)), 1e6 * P.T_SAMPLE,
        P.T_SAMPLE / (tau * np.log(2 ** (P.NBITS + 1)))))

# --- 7. Monte Carlo -------------------------------------------------------
say("\n--- 7. Monte Carlo: R al 1 %, C al 5 %, 200 corridas ---------------")
mc = {}
for grid in ("Colombia", "Chile"):
    steps = run("uPMU_AFE_mc_%s.cir" % grid)
    g = P.GRIDS[grid]
    f0 = g["f0"]
    rows = []
    for s in steps:
        f = s["frequency"].real
        k = int(np.argmin(abs(f - f0)))
        rows.append((s["V(adcv)"][k], s["V(adci)"][k]))
    hv = np.array([r[0] for r in rows]) / g["Vrms"]
    hi = np.array([r[1] for r in rows]) / g["In_rms"]
    nv, ni = h_v(f0, grid=grid), h_i(f0)
    emv = 100 * (abs(hv) / abs(nv) - 1)
    emi = 100 * (abs(hi) / abs(ni) - 1)
    epv = np.degrees(np.angle(hv / nv))
    epi = np.degrees(np.angle(hi / ni))
    dphi = np.degrees(np.angle(hv / hi)) - np.degrees(np.angle(nv / ni))
    mc[grid] = dict(emv=emv, emi=emi, epv=epv, epi=epi, dphi=dphi, n=len(rows))
    say("%s (%g Hz, %d corridas)  [error respecto al nominal, SIN calibrar]" % (grid, f0, len(rows)))
    for lab, a in (("modulo V [%]", emv), ("modulo I [%]", emi),
                   ("fase V [deg]", epv), ("fase I [deg]", epi),
                   ("fase V-I [deg]", dphi)):
        say("  %-16s media %+8.4f  sigma %7.4f  p95|.| %7.4f  max|.| %7.4f" % (
            lab, a.mean(), a.std(), np.percentile(abs(a), 95), abs(a).max()))

# --- 8. Graficas ----------------------------------------------------------
say("\n--- 8. Graficas ----------------------------------------------------")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(3, 1, figsize=(9, 10))
for lab, d, f, node, h0 in (("canal V", acv, fv, "V(adcv)", h60),
                            ("canal I", aci, fi, "V(adci)", abs(at(aci, "V(adci)", fi, 60.0)))):
    ax[0].semilogx(f, 20 * np.log10(abs(d[node]) / h0), label=lab + " (CT real)")
    ax[1].semilogx(f, np.degrees(np.angle(d[node])), label=lab + " (CT real)")
for lab, d, f, node in (("canal V", acv0, f0v, "V(adcv)"), ("canal I", aci0, f0i, "V(adci)")):
    ax[1].semilogx(f, np.degrees(np.angle(d[node])), "--", lw=1, label=lab + " (CT ideal)")
ax[0].set_ylabel("modulo [dB rel. 60 Hz]"); ax[0].grid(True, which="both", alpha=.3)
ax[0].legend(fontsize=8)
ax[0].set_title("Modulo, referido a 60 Hz", fontsize=10)
ax[1].set_ylabel("fase [deg]"); ax[1].set_xlabel("frecuencia [Hz]")
ax[1].set_title("Fase", fontsize=10)
ax[1].grid(True, which="both", alpha=.3); ax[1].legend(fontsize=8)
for a in ax[:2]:
    for ff in (50, 60, 4222, 7500):
        a.axvline(ff, color="k", lw=.5, alpha=.3)

# Panel 3: la zona util, donde esta el hallazgo (decimas de grado).
z = (fv >= 40) & (fv <= 70)
zi = (fi >= 40) & (fi <= 70)
ax[2].plot(fv[z], np.degrees(np.angle(acv["V(adcv)"][z])), label="V (CT real)")
ax[2].plot(fi[zi], np.degrees(np.angle(aci["V(adci)"][zi])), label="I (CT real)")
ax[2].plot(fv[z], np.degrees(np.angle(acv["V(adcv)"][z] / aci["V(adci)"][zi])),
           "k", lw=2, label="V - I (CT real)")
ax[2].plot(f0v[(f0v >= 40) & (f0v <= 70)],
           np.degrees(np.angle(acv0["V(adcv)"][(f0v >= 40) & (f0v <= 70)])),
           "--", lw=1, label="V = I (CT ideal)")
ax[2].axhline(0, color="k", lw=.5)
for ff in (50, 60):
    ax[2].axvline(ff, color="k", lw=.5, alpha=.4)
ax[2].set_xlabel("frecuencia [Hz]"); ax[2].set_ylabel("fase [deg]")
ax[2].set_title("Banda de trabajo: con el transformador ideal la fase V-I era 0"
                " exacta; con el real, no", fontsize=10)
ax[2].grid(alpha=.3); ax[2].legend(fontsize=8)
fig.suptitle("Respuesta en frecuencia del front-end analogico del uPMU", fontsize=12)
fig.tight_layout(); fig.savefig(FIGURAS / "ltspice_ac.png", dpi=130); plt.close(fig)
say("  ltspice_ac.png")

fig, ax = plt.subplots(2, 1, figsize=(9, 7))
for k, (grid, suf) in enumerate((("Colombia", ""), ("Chile", "_Chile"))):
    for tag, ls in (("", "-"), ("_ovl", "--")):
        d = LR.read(HERE / ("uPMU_AFE_tran%s%s.raw" % (suf, tag)))[0]
        t = d["time"]
        # Ventana relativa: dos ciclos, saltando el primero (la ventana
        # guardada empieza en SETTLE, no en 0).
        f0 = P.GRIDS[grid]["f0"]
        t0 = t[0] + 1.0 / f0
        m = (t >= t0) & (t <= t0 + 2.0 / f0)
        ax[k].plot(1e3 * (t[m] - t0), d["V(adcv)"][m], ls, lw=1,
                   label="V(adcv)" + (" 120 %" if tag else " nominal"))
        ax[k].plot(1e3 * (t[m] - t0), d["V(adci)"][m], ls, lw=1,
                   label="V(adci)" + (" 200 %" if tag else " nominal"))
    ax[k].axhline(0, color="r", lw=.8); ax[k].axhline(P.VDDA, color="r", lw=.8)
    ax[k].axhline(P.VCM, color="k", lw=.5, alpha=.5)
    ax[k].set_title("%s (%g Hz, %g V)" % (grid, P.GRIDS[grid]["f0"], P.GRIDS[grid]["Vrms"]))
    ax[k].set_ylabel("V en el pin"); ax[k].grid(alpha=.3); ax[k].legend(fontsize=7, ncol=2)
    ax[k].set_ylim(-0.2, 3.5)
ax[1].set_xlabel("t [ms] desde el inicio de la ventana en regimen")
fig.suptitle("Tension en el pin del ADC: carga nominal y sobrecarga", fontsize=12)
fig.tight_layout(); fig.savefig(FIGURAS / "ltspice_tran.png", dpi=130); plt.close(fig)
say("  ltspice_tran.png")

fig, ax = plt.subplots(2, 3, figsize=(12, 6))
for r, grid in enumerate(("Colombia", "Chile")):
    m = mc[grid]
    for c, (lab, key, unit) in enumerate((("modulo V", "emv", "%"), ("modulo I", "emi", "%"),
                                          ("fase V-I", "dphi", "deg"))):
        ax[r, c].hist(m[key], bins=30, color="C%d" % c, alpha=.8)
        ax[r, c].set_title("%s - %s [%s]" % (grid, lab, unit), fontsize=9)
        ax[r, c].set_xlabel("sigma = %.4f" % m[key].std(), fontsize=8)
        ax[r, c].grid(alpha=.3)
fig.suptitle("Dispersion por tolerancias de los componentes: R al 1 %, C al 5 %"
             " (200 corridas, sin calibrar)", fontsize=12)
fig.tight_layout(); fig.savefig(FIGURAS / "ltspice_montecarlo.png", dpi=130); plt.close(fig)
say("  ltspice_montecarlo.png")

(RESULTADOS / "results_ltspice.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
print("\n-> results_ltspice.txt")
