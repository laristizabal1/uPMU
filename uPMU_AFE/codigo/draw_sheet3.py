# -*- coding: utf-8 -*-
"""Hoja 3/3 - el circuito tal como lo simula LTspice (valores de params.py).

No es una hoja de montaje: incluye elementos que son del MODELO (la inductancia
magnetizante del transformador, la red de muestreo interna del ADC) y que no se
compran ni se sueldan.  La hoja de montaje es la 1/3.
"""
import numpy as np

import params as P
from schlib import *


def k(v, unit="Ω"):
    if v >= 1e3:
        return ("%g" % (v / 1e3)).replace(".", ",") + " k" + unit
    return ("%g" % v).replace(".", ",") + " " + unit


def ct_phase(f, rw, lm, rb):
    return P.ct_phase_deg(f, rw, lm, rb)


S = Sheet(70, 44, scale=0.36)
sx = S.text

YV, YVCM, YI = 30.0, 24.0, 18.0     # fila canal V, riel VCM, fila canal I

# ---------------- Encabezado --------------------------------------------------
sx(2, 42.6, "uPMU prototipo — Hoja 3/3: el circuito que simula LTspice",
   size=15, ha="left", weight="bold")
sx(2, 41.3, "Mismo circuito que los netlists de netlists/*.cir  ·  valores = codigo/params.py  ·  "
            "los elementos en gris son del MODELO: no se compran ni se sueldan",
   size=10, ha="left", color=NOTE)

S.box(2, 34.6, 33.0, 5.6, fc="#f4f7fb", ec="#9db3cc", lw=1.0)
sx(2.6, 39.3, "Qué cambia respecto de la hoja 1 (de montaje)", size=10, ha="left", weight="bold")
sx(2.6, 36.8,
   "1. Los transformadores ya no son ideales: llevan magnetizante Lm y devanado Rw.\n"
   "    Adelantan la fase ε = (Rw + Rb)/(ω·Lm), que depende de la frecuencia.\n"
   "2. El pin del ADC lleva su red de muestreo (abajo), no solo la parásita.\n"
   "3. Lm sale del límite de la hoja de datos, no de una medida:  CONFIRMAR.",
   size=9.4, ha="left")

S.box(36.5, 34.6, 31.5, 5.6, fc="#fff8ec", ec="#d9b36c", lw=1.0)
sx(37.1, 39.3, "Consecuencia medida en la simulación", size=10, ha="left", weight="bold")
sx(37.1, 36.8,
   "Con el transformador ideal la fase V−I daba 0,0000° exactos.\n"
   "Con el modelo real:  −%.4f° a 50 Hz   y   −%.4f° a 60 Hz.\n"
   "La calibración de un punto la quita en f0, pero no fuera de f0:\n"
   "a f0 ± 5 Hz el TVE pasa de ~0,01 %% a 0,15–0,27 %% (límite de la norma: 1 %%)." % (
       abs(ct_phase(50, P.RW_I, P.LM_I, P.RB_I) - ct_phase(50, P.RW_V, P.LM_V, P.RB_V)),
       abs(ct_phase(60, P.RW_I, P.LM_I, P.RB_I) - ct_phase(60, P.RW_V, P.LM_V, P.RB_V))),
   size=9.4, ha="left")

# ---------------- Riel VCM ----------------------------------------------------
S.wire((13, YVCM), (34, YVCM), color=NET)
S.netlabel(13, YVCM, "VCM = 1,65 V", ha="left", dx=-0.2, dy=-0.9, size=9.4)

GRIS = "#8a8a8a"


def modelo_ct(x0, y, etiqueta):
    """Fuente ideal del secundario del transformador (simbolo)."""
    # fuente ideal del secundario (circulo con flecha)
    S.ax.add_patch(Circle((x0, y), 1.0, fc="white", ec=INK, lw=LW, zorder=3))
    S.wire((x0, y - 0.55), (x0, y + 0.55))
    S.wire((x0 - 0.3, y + 0.25), (x0, y + 0.55))
    S.wire((x0 + 0.3, y + 0.25), (x0, y + 0.55))
    sx(x0, y + 1.6, etiqueta, size=8.6, ha="center", color=NOTE)
    # de la fuente al nodo del secundario
    S.wire((x0 + 1.0, y), (x0 + 4.0, y))
    S.dot(x0 + 4.0, y)
    return x0 + 4.0


def rama_vertical(x, y_nodo, y_rail, tipo, etiqueta, gris=False):
    """Elemento vertical entre la fila del canal y el riel VCM."""
    y1, y2 = (y_nodo, y_rail) if y_nodo > y_rail else (y_nodo, y_rail)
    f = {"res": S.res, "cap": S.cap}[tipo]
    f((x, y1), (x, y2), etiqueta, side=1, off=0.9)
    S.dot(x, y_nodo)


# ============================= CANAL DE TENSIÓN ================================
sx(2, 32.6, "CANAL DE TENSIÓN", size=10.5, ha="left", weight="bold", color="#8a1c1c")

S.box(2, YV - 1.6, 8.0, 3.2, fc="#f7f7f7", ec=GRIS, lw=1.2)
sx(6.0, YV + 0.45, "red %g V · Rp %s" % (P.GRIDS["Colombia"]["Vrms"], k(P.GRIDS["Colombia"]["Rp"])),
   size=8.8, ha="center")
sx(6.0, YV - 0.75, "primario ZMPT101B", size=8.8, ha="center", color=NOTE)
S.wire((10.0, YV), (12.0, YV))

nsv = modelo_ct(13.0, YV, "1:1 ideal (F)")

# Lm del canal V, del nodo nsv al riel VCM
S.wire((nsv, YV), (nsv, YV - 1.0))
yt, yb = S.coil(nsv, YV - 1.0, loops=4, d=0.8, bulge=+1)
S.wire((nsv, yb), (nsv, YVCM))
sx(nsv - 0.8, (YV + YVCM) / 2 - 0.5, "Lmv\n%.0f H" % P.LM_V, size=8.6, ha="right", color=GRIS)

S.res((nsv, YV), (nsv + 5.0, YV), "Rwv  %s" % k(P.RW_V), side=1, off=0.95, body=2.0)
bv = nsv + 5.0
S.dot(bv, YV)
sx(bv - 2.5, YV + 1.7, "devanado (modelo)", size=8.2, ha="center", color=GRIS)

rama_vertical(bv, YV, YVCM, "res", "Rbv  %s  1 %%" % k(P.RB_V))
S.res((bv, YV), (bv + 6.0, YV), "Rfv  %s  1 %%" % k(P.RF_V), side=1, off=0.95, body=2.4)
nv = bv + 6.0
S.dot(nv, YV)
rama_vertical(nv, YV, YVCM, "cap", "Cfv  10 nF  2 %")
S.res((nv, YV), (nv + 6.0, YV), "Rsv  %s" % k(P.RS_ADC), side=1, off=0.95, body=2.4)
adcv = nv + 6.0
S.wire((adcv, YV), (52.0, YV))
S.netlabel(45.0, YV, "ADC_V", ha="center", dx=0, dy=0.9, size=9.4)
S.terminal(52.0, YV, "")

# parasita del pin y clamps del canal V
S.dot(40.0, YV)
S.cap((40.0, YV), (40.0, YV - 3.4), "Cpv  %g pF" % (P.C_ADC_PAR * 1e12), side=1, off=0.95)
S.ground(40.0, YV - 3.4)
S.dot(44.0, YV)
S.diode((44.0, YV), (44.0, YV + 3.0), "D1v", side=1, off=0.8)
S.rail_flag(44.0, YV + 3.0, "+3V3A")
S.dot(48.0, YV)
S.diode((48.0, YV - 3.4), (48.0, YV), "D2v", side=1, off=0.8)
S.ground(48.0, YV - 3.4)

# ============================= CANAL DE CORRIENTE ==============================
sx(2, YI + 2.6, "CANAL DE CORRIENTE", size=10.5, ha="left", weight="bold", color="#8a1c1c")

S.box(2, YI - 1.6, 8.0, 3.2, fc="#f7f7f7", ec=GRIS, lw=1.2)
sx(6.0, YI + 0.45, "SCT-013   2000 : 1", size=8.8, ha="center")
sx(6.0, YI - 0.75, "35 A rms nominal", size=8.8, ha="center", color=NOTE)
S.wire((10.0, YI), (12.0, YI))

nsi = modelo_ct(13.0, YI, "Ip/2000 ideal")

S.wire((nsi, YI), (nsi, YI + 1.0))
yt, yb = S.coil(nsi, YVCM, loops=4, d=0.8, bulge=+1)
S.wire((nsi, YI + 1.0), (nsi, yb))
sx(nsi - 0.8, (YI + YVCM) / 2 - 0.5, "Lmi\n%.2f H" % P.LM_I, size=8.6, ha="right", color=GRIS)

S.res((nsi, YI), (nsi + 5.0, YI), "Rwi  %s" % k(P.RW_I), side=-1, off=0.95, body=2.0)
bi = nsi + 5.0
S.dot(bi, YI)
rama_vertical(bi, YI, YVCM, "res", "Rbi  %s  1 %%" % k(P.RB_I))
S.res((bi, YI), (bi + 6.0, YI), "Rfi  %s  1 %%" % k(P.RF_I), side=-1, off=0.95, body=2.4)
ni = bi + 6.0
S.dot(ni, YI)
rama_vertical(ni, YI, YVCM, "cap", "Cfi  10 nF  2 %")
S.res((ni, YI), (ni + 6.0, YI), "Rsi  %s" % k(P.RS_ADC), side=-1, off=0.95, body=2.4)
adci = ni + 6.0
S.wire((adci, YI), (52.0, YI))
S.netlabel(45.0, YI, "ADC_I", ha="center", dx=0, dy=-1.2, size=9.4)
S.terminal(52.0, YI, "")

S.dot(40.0, YI)
S.cap((40.0, YI), (40.0, YI - 3.4), "Cpi  %g pF" % (P.C_ADC_PAR * 1e12), side=1, off=0.95)
S.ground(40.0, YI - 3.4)
S.dot(44.0, YI)
S.diode((44.0, YI), (44.0, YI + 3.0), "D1i", side=1, off=0.8)
S.rail_flag(44.0, YI + 3.0, "+3V3A")
S.dot(48.0, YI)
S.diode((48.0, YI - 3.4), (48.0, YI), "D2i", side=1, off=0.8)
S.ground(48.0, YI - 3.4)

# ---------------- Tabla del modelo del transformador --------------------------
S.box(53.5, 20.5, 14.5, 12.0, fc="#fbf7fb", ec="#a98bb0", lw=1.0)
sx(54.1, 31.6, "Modelo del transformador", size=9.6, ha="left", weight="bold")
sx(54.1, 25.9,
   "ε = (Rw + Rb) / (ω·Lm)   [adelanto]\n\n"
   "Lm NO se inventó: se derivó del\n"
   "error de fase de la hoja de datos.\n"
   "ZMPT101B: ≤ 20′ con 100 Ω de carga\n"
   "(aquí la carga es 470 Ω = 4,7×).\n"
   "SCT-013: la hoja no lo publica;\n"
   "se mantiene el supuesto de 1°.\n\n"
   "        50 Hz      60 Hz\n"
   "ε_V   +%.3f°    +%.3f°\n"
   "ε_I   +%.3f°    +%.3f°\n"
   "RC    %.3f°    %.3f°" % (
       ct_phase(50, P.RW_V, P.LM_V, P.RB_V), ct_phase(60, P.RW_V, P.LM_V, P.RB_V),
       ct_phase(50, P.RW_I, P.LM_I, P.RB_I), ct_phase(60, P.RW_I, P.LM_I, P.RB_I),
       P.rc_phase_deg(50, P.RB_V, P.RF_V), P.rc_phase_deg(60, P.RB_V, P.RF_V)),
   size=8.6, ha="left")

# ---------------- Modelo de entrada del ADC -----------------------------------
YA = 9.0
sx(2, 13.2, "RED DE MUESTREO DEL ADC  (modelo; está dentro del STM32F303K8)",
   size=10.5, ha="left", weight="bold", color="#8a1c1c")

S.terminal(4.0, YA, "")
sx(4.0, YA + 1.2, "pin ADC", size=8.8, ha="center", color=NET)
S.wire((4.0, YA), (9.0, YA))
S.dot(7.0, YA)
S.cap((7.0, YA), (7.0, YA - 3.2), "C_par  %g pF\n(pad + PCB)" % (P.C_ADC_PAR * 1e12), side=1, off=1.1)
S.ground(7.0, YA - 3.2)

# interruptor de muestreo
S.wire((9.0, YA), (11.0, YA))
S.dot(11.0, YA)
S.wire((11.0, YA), (13.4, YA + 1.1), lw=1.6)
S.dot(14.0, YA, 0.12)
S.wire((14.0, YA), (16.0, YA))
sx(12.5, YA + 2.3, "muestreo: %.2f µs\n(61,5 ciclos a %g MHz)" % (1e6 * P.T_SAMPLE, P.F_ADC_CLK / 1e6),
   size=8.6, ha="center", color=NOTE)
S.res((16.0, YA), (22.0, YA), "R_ADC  %s  CONFIRMAR" % k(P.R_ADC), side=1, off=0.95, body=2.4)
S.dot(22.0, YA)
S.cap((22.0, YA), (22.0, YA - 3.2), "C_SH  %g pF\nCONFIRMAR" % (P.C_ADC_SH * 1e12), side=1, off=1.1)
S.ground(22.0, YA - 3.2)

_tau = (P.RS_ADC + P.R_ADC) * P.C_ADC_SH
S.box(26.5, 4.2, 41.5, 9.2, fc="#f2f8f2", ec="#4a7a4a", lw=1.0)
sx(27.1, 12.4, "¿Asientan 12 bits en la ventana de muestreo?   Sí, con 46× de margen",
   size=9.8, ha="left", weight="bold")
sx(27.1, 8.0,
   "τ = (Rsv + R_ADC) · C_SH = (%s + %s) · %g pF = %.1f ns\n"
   "12 bits piden ln(2¹³)·τ = %.0f ns;  la ventana dura %.2f µs  →  margen %.0f×\n\n"
   "Simulado con el interruptor real (netlists/uPMU_AFE_adcsh.cir), 60 ventanas:\n"
   "error entre C_SH y el pin al cerrar = %.4f LSB (canal V), %.4f LSB (canal I).\n\n"
   "Ayuda que Cfv = 10 nF sea 2000× el condensador de muestreo: la carga que se\n"
   "redistribuye vale 5 pF / 10 nF = 5·10⁻⁴ de la diferencia entre muestras." % (
       k(P.RS_ADC), k(P.R_ADC), P.C_ADC_SH * 1e12, 1e9 * _tau,
       1e9 * _tau * np.log(2 ** (P.NBITS + 1)), 1e6 * P.T_SAMPLE,
       P.T_SAMPLE / (_tau * np.log(2 ** (P.NBITS + 1))),
       0.0028, 0.0017),
   size=9.0, ha="left")

sx(2, 1.2, "Hoja de simulación, no de montaje: Lm, Rw, R_ADC y C_SH son elementos del modelo. "
           "Para armar, usar la hoja 1/3.  Los puntos CONFIRMAR están en docs/RESULTADOS_LTspice.pdf.",
   size=8.4, ha="left", color=NOTE, style="italic")

S.save("uPMU_AFE_hoja3_modelo_ltspice")
print("hoja 3 lista")
