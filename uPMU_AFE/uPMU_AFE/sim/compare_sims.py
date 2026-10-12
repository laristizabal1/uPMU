# -*- coding: utf-8 -*-
"""Compara LTspice contra ngspice contra el modelo cerrado de Python.

Usa los .raw que dejo run_ltspice.py y corre los mismos netlists en ngspice
(WASM, via ngspice_runner).  Escribe results_compare.txt.

    python compare_sims.py              # corre ngspice y compara
    python compare_sims.py --no-run     # usa los ng_*.json que ya existan
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

import ltspice_raw as LR
import params as P
from afe_model import h_v, h_i            # modelo cerrado exacto

HERE = Path(__file__).parent
RUNNER = HERE.parent / "ngspice_runner"
DO_RUN = "--no-run" not in sys.argv
OUT = []

# Umbrales del enunciado para marcar una diferencia como relevante.
TOL_MAG = 0.1      # %
TOL_PH = 0.05      # grados


def say(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s)


def ngspice(cir, out):
    """Corre un netlist en ngspice y devuelve {nombre: np.array}."""
    j = HERE / out
    if DO_RUN:
        r = subprocess.run(["node", "run.mjs", str(HERE / cir), str(j)],
                           cwd=RUNNER, capture_output=True, text=True, shell=True)
        if not j.exists():
            say("  !! ngspice fallo en %s: %s" % (cir, (r.stderr or r.stdout)[-400:]))
            return None
    if not j.exists():
        return None
    d = json.load(open(j))
    out_d = {}
    for x in d["data"]:
        v = x["values"]
        out_d[x["name"]] = (np.array([complex(y["real"], y["img"]) for y in v])
                            if isinstance(v[0], dict) else np.array(v, dtype=float))
    return out_d


def get(d, node):
    """ngspice pasa los nombres a minusculas; LTspice los conserva."""
    if node in d:
        return d[node]
    low = {k.lower(): v for k, v in d.items()}
    return low[node.lower()]


def at(d, node, f, fw):
    y = get(d, node)
    return np.interp(fw, f, y.real) + 1j * np.interp(fw, f, y.imag)


def flag(dmag_pct, dph_deg):
    out = []
    if abs(dmag_pct) > TOL_MAG:
        out.append("MODULO>%.1f%%" % TOL_MAG)
    if abs(dph_deg) > TOL_PH:
        out.append("FASE>%.2fdeg" % TOL_PH)
    return ("  <<< " + ", ".join(out)) if out else ""


say("=" * 78)
say("LTspice vs ngspice vs modelo cerrado de Python  (mismos netlists)")
say("Umbrales del enunciado: %.1f %% en modulo, %.2f grados en fase" % (TOL_MAG, TOL_PH))
say("=" * 78)

# --- AC por canal ---------------------------------------------------------
say("\n--- AC: modulo y fase en el nodo del ADC ---------------------------")
say("%-8s %-5s %-14s %-14s %-14s %-9s %-9s" % (
    "canal", "f[Hz]", "LTspice |H|", "ngspice |H|", "Python |H|",
    "dMod[%]", "dFase[deg]"))
ac = {}
for tag, node, hf in (("V", "V(adcv)", h_v), ("I", "V(adci)", h_i)):
    lt = LR.one(HERE / ("uPMU_AFE_ac_%s.raw" % tag))
    ng = ngspice("uPMU_AFE_ac_%s.cir" % tag, "ng_ac_%s.json" % tag)
    flt = lt["frequency"].real
    ac[tag] = (lt, ng, flt)
    for f0 in (50.0, 60.0):
        a = at(lt, node, flt, f0)
        p = hf(f0)
        if ng is None:
            say("%-8s %-5g %.6e   (ngspice no disponible)" % (tag, f0, abs(a)))
            continue
        fng = ng["frequency"].real
        b = at(ng, node, fng, f0)
        dm = 100 * (abs(b) / abs(a) - 1)
        dp = np.degrees(np.angle(b / a))
        say("%-8s %-5g %.6e   %.6e   %.6e   %+8.4f  %+8.4f%s" % (
            tag, f0, abs(a), abs(b), abs(p), dm, dp, flag(dm, dp)))
        say("%14s fase: LTspice %+8.4f  ngspice %+8.4f  Python %+8.4f deg" % (
            "", np.degrees(np.angle(a)), np.degrees(np.angle(b)), np.degrees(np.angle(p))))

# diferencia LTspice vs Python sobre toda la banda util
say("\nLTspice vs el modelo cerrado de Python, por banda:")
for tag, node, hf in (("V", "V(adcv)", h_v), ("I", "V(adci)", h_i)):
    lt, ng, flt = ac[tag]
    for lo, hi in ((10, 100), (100, 1000), (1000, 5000), (5000, 100000)):
        m = (flt >= lo) & (flt <= hi)
        ref = hf(flt[m])
        sim = lt[node][m]
        dm = abs(abs(sim) / abs(ref) - 1) * 100
        dp = abs(np.degrees(np.angle(sim / ref)))
        k = int(np.argmax(dp))
        say("  canal %s %6g-%6g Hz: max dMod %.4f %%, max dFase %.4f deg (a %.0f Hz)%s" % (
            tag, lo, hi, dm.max(), dp.max(), flt[m][k], flag(dm.max(), dp.max())))
say("  Origen conocido de la diferencia a alta frecuencia: el modelo cerrado no")
say("  incluye la capacidad de juntura de los 1N4148 (Cjo 4 pF, ~2,5 pF con 1,65 V")
say("  de inversa, dos por nodo).  Suma ~5 pF al pin: el polo del pin pasa de")
say("  23 MHz a 13 MHz, lo que da ~0,02 deg a 5 kHz y ~0,0003 deg a 60 Hz.")

# --- fase V-I -------------------------------------------------------------
say("\n--- Fase V-I (lo que de verdad importa para la potencia) -----------")
ltv, ngv, fv = ac["V"]
lti, ngi, fi = ac["I"]
for f0 in (50.0, 60.0):
    a = np.degrees(np.angle(at(ltv, "V(adcv)", fv, f0) / at(lti, "V(adci)", fi, f0)))
    p = np.degrees(np.angle(h_v(f0) / h_i(f0)))
    if ngv is not None and ngi is not None:
        b = np.degrees(np.angle(
            at(ngv, "V(adcv)", ngv["frequency"].real, f0)
            / at(ngi, "V(adci)", ngi["frequency"].real, f0)))
    else:
        b = float("nan")
    say("  %g Hz: LTspice %+.4f  ngspice %+.4f  Python %+.4f deg" % (f0, a, b, p))

# --- Transitorio ----------------------------------------------------------
say("\n--- Transitorio: recorrido en el pin del ADC -----------------------")
say("%-10s %-5s %-24s %-24s %s" % ("red", "carga", "LTspice V / I",
                                   "ngspice V / I", "dif. maxima"))
for grid in ("Colombia", "Chile"):
    suf = "" if grid == "Colombia" else "_" + grid
    for tag in ("", "_ovl"):
        cir = "uPMU_AFE_tran%s%s.cir" % (suf, tag)
        lt = LR.one(HERE / (cir[:-4] + ".raw"))
        ng = ngspice(cir, "ng_tran%s%s.json" % (suf, tag))
        # Se descarta un ciclo desde el inicio de la ventana en ambos, para
        # comparar regimen con regimen y no el primer instante.
        def lo(d, k):
            tt = get(d, "time")
            y = get(d, k)[tt >= tt[0] + 1.0 / P.GRIDS[grid]["f0"]]
            return y.min(), y.max()
        lv, hv_ = lo(lt, "V(adcv)")
        li, hi_ = lo(lt, "V(adci)")
        if ng is None:
            say("%-10s %-5s %6.3f..%6.3f / %6.3f..%6.3f   (ngspice no disponible)" % (
                grid, tag or "nom", lv, hv_, li, hi_))
            continue
        nv, nh = lo(ng, "V(adcv)")
        ni, nhi = lo(ng, "V(adci)")
        d = max(abs(nv - lv), abs(nh - hv_), abs(ni - li), abs(nhi - hi_))
        say("%-10s %-5s %6.3f..%6.3f / %6.3f..%6.3f  %6.3f..%6.3f / %6.3f..%6.3f  %.3f mV" % (
            grid, tag or "nom", lv, hv_, li, hi_, nv, nh, ni, nhi, 1e3 * d))

# --- Contra la cadena completa de Python ---------------------------------
say("\n--- Monte Carlo sin calibrar: LTspice vs simulate_chain.py ---------")
say("No son la misma cantidad y no tienen por que coincidir:")
say("  * LTspice da error de MODULO y de FASE por separado, y solo con la")
say("    tolerancia de R (1 %) y C (5 %), que es lo que el netlist puede variar.")
say("  * simulate_chain.py da TVE (modulo y fase juntos) y ademas mueve la")
say("    relacion del CT (1 %) y la inductancia magnetizante (30 %).")
try:
    ch = json.load(open(HERE / "results_chain.json"))
except Exception as e:
    say("  (no pude leer results_chain.json: %s)" % e)
    ch = None
if ch:
    for grid in ("Colombia", "Chile"):
        u = ch[grid]["uncal_p95"]
        say("  %-8s Python TVE p95 sin calibrar: V = %.2f %%, I = %.2f %%" % (
            grid, u[0], u[1]))
    say("  LTspice, error de modulo sin calibrar p95: V = 1,60 %, I = 0,96 %.")
    say("  Se reconcilian sumando en cuadratura los terminos que faltan (sin")
    say("  calibrar, el desfase del CT entra entero en el TVE: TVE ~ fase[rad]):")
    say("    canal V: modulo 1,60 % + fase 0,689 deg = 1,20 %  ->  2,00 %")
    say("             contra 2,11 % de Python.")
    say("    canal I: modulo 0,96 % + CT_RATIO 0,95 % + fase 0,833 deg = 1,45 %")
    say("             ->  1,97 %, contra 2,32 % de Python.")
    say("  Es del orden correcto; no coincide al decimal porque el p95 de una")
    say("  suma no es la suma en cuadratura de los p95.")

(HERE / "results_compare.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
print("\n-> results_compare.txt")
