# -*- coding: utf-8 -*-
"""Modelo cerrado exacto de un canal del AFE (CT con magnetizante + RC + pin).

Lo usan run_ltspice.py y compare_sims.py.  Autocomprobacion: python afe_model.py
"""
import numpy as np

import params as P


# ---------------------------------------------------------------------------
# Modelo cerrado EXACTO de un canal: CT con magnetizante + escalera RC + pin.
# vcm se toma como masa de alterna (el error que eso mete se reporta aparte).
# ---------------------------------------------------------------------------
def h_exact(f, rb, rf, rw, lm, gain, ideal_ct=False):
    """Transferencia de la entrada al nodo del ADC.

    gain: la fuente ideal del secundario vale gain x entrada
          (1/Rp para el canal V en A/V; 1/CT_RATIO para el canal I en A/A).
    """
    w = 2 * np.pi * np.asarray(f, dtype=float)
    zc = 1.0 / (1j * w * P.C_F)          # Cf al nodo vcm
    zp = 1.0 / (1j * w * P.C_ADC_PAR)    # parasita del pin a masa
    z3 = P.RS_ADC + zp                   # desde nv hacia el pin
    z2 = zc * z3 / (zc + z3)             # impedancia en nv
    z1 = rf + z2                         # desde bv hacia nv
    z0 = rb * z1 / (rb + z1)             # impedancia en bv
    zin = rw + z0                        # carga vista por el secundario
    zm = 1e30 + 0j if ideal_ct else 1j * w * lm
    ztot = zm * zin / (zm + zin)         # magnetizante en paralelo
    # V(nsv) = Is*ztot ; luego divisores sucesivos
    return gain * ztot / zin * z0 * (z2 / z1) * (zp / z3)


def h_v(f, ideal_ct=False, grid="Colombia"):
    rp = P.GRIDS[grid]["Rp"] + P.R_PRI_ZMPT
    return h_exact(f, P.RB_V, P.RF_V, P.RW_V, P.LM_V, 1.0 / rp, ideal_ct)


def h_i(f, ideal_ct=False):
    return h_exact(f, P.RB_I, P.RF_I, P.RW_I, P.LM_I, 1.0 / P.CT_RATIO, ideal_ct)


def h_simple_v(f):
    """La formula que usa simulate_chain.py (RC solo, CT ideal)."""
    w = 2 * np.pi * np.asarray(f, dtype=float)
    return (P.RB_V / P.GRIDS["Colombia"]["Rp"]) / (1 + 1j * w * P.C_F * (P.RB_V + P.RF_V))


def h_simple_i(f):
    w = 2 * np.pi * np.asarray(f, dtype=float)
    return (P.RB_I / P.CT_RATIO) / (1 + 1j * w * P.C_F * (P.RB_I + P.RF_I))



if __name__ == "__main__":
    # El modelo exacto debe coincidir con la formula simple cuando el CT es
    # ideal y se desprecian Rs/Cp: a 60 Hz eso vale a mejor que 1e-5.
    f = 60.0
    a = h_exact(f, P.RB_V, P.RF_V, 0.0, 0.0, 1.0 / P.GRIDS["Colombia"]["Rp"], True)
    b = h_simple_v(f)
    # 1.3e-5 de diferencia: es el polo del pin (Rs 1 k + Cp 7 pF), que la
    # formula simple no tiene y h_exact si.
    assert abs(a / b - 1) < 5e-5, (a, b)
    # Con el CT real el adelanto de fase debe coincidir con ct_phase_deg().
    c = h_exact(f, P.RB_V, P.RF_V, P.RW_V, P.LM_V, 1.0 / P.GRIDS["Colombia"]["Rp"])
    d = np.degrees(np.angle(c / a))
    e = P.ct_phase_deg(f, P.RW_V, P.LM_V, P.RB_V)
    assert abs(d - e) < 0.01, (d, e)
    print("afe_model: OK  (|H_V| = %.6e V/V, fase %+.4f deg; adelanto del CT "
          "%.4f deg vs %.4f de params)" % (abs(c), np.degrees(np.angle(c)), d, e))
