# -*- coding: utf-8 -*-
"""Compara el transitorio de ngspice con el modelo cerrado, muestra por muestra.

Complementa compare_sims.py (que compara picos y la respuesta AC): aqui se
evalua el modelo en los MISMOS instantes en que muestrea el ADC y se mide el
error punto a punto, que es lo que de verdad ve el firmware.

    python verify_spice.py          # usa los out_tran*.json de run_all.sh
"""
import json
from pathlib import Path

import numpy as np

import params as P
from afe_model import h_i, h_v

HERE = Path(__file__).parent


def load(fn):
    r = json.load(open(HERE / fn))
    return {x["name"].lower(): np.array(x["values"], dtype=float) for x in r["data"]}


print("--- ngspice vs modelo cerrado exacto (CT con magnetizante + RC + pin) ---")
for grid, fn in (("Colombia", "out_tran.json"), ("Chile", "out_tran_Chile.json")):
    try:
        d = load(fn)
    except FileNotFoundError:
        print("%-8s falta %s (corre run_all.sh)" % (grid, fn))
        continue
    g = P.GRIDS[grid]
    f = g["f0"]
    w = 2 * np.pi * f
    t = d["time"]
    # La ventana guardada empieza ya asentada; se descarta un ciclo por si acaso.
    ts = np.arange(t[0] + 1.0 / f, t[-1], 1.0 / P.FS)
    vs = np.interp(ts, t, d["v(adcv)"])
    i_s = np.interp(ts, t, d["v(adci)"])
    # Las fuentes del netlist son SIN(...), de ahi el imag().  La corriente
    # lleva el desfase phii = -30 grados del netlist.
    vm = P.VCM + np.imag(np.sqrt(2) * g["Vrms"] * h_v(f, grid=grid) * np.exp(1j * w * ts))
    im = P.VCM + np.imag(np.sqrt(2) * g["In_rms"] * h_i(f)
                         * np.exp(1j * (w * ts + np.radians(-30.0))))
    print("%-8s max|dV| = %.3f mV, max|dI| = %.3f mV  (1 LSB = %.3f mV)" % (
        grid, 1e3 * np.max(abs(vs - vm)), 1e3 * np.max(abs(i_s - im)), 1e3 * P.LSB))
    print("%-8s pin ADC: V %.3f..%.3f V, I %.3f..%.3f V | margen %.3f V a 0, %.3f V a %.1f V" % (
        "", vs.min(), vs.max(), i_s.min(), i_s.max(),
        min(vs.min(), i_s.min()), P.VDDA - max(vs.max(), i_s.max()), P.VDDA))
