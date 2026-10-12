"""Hoja 1/2 - front-end analogico del uPMU (valores tomados de sim/params.py)."""
import numpy as np
import params as P
from schlib import *

def k(v, unit="Ω"):
    if v >= 1e3:
        return ("%g" % (v / 1e3)).replace(".", ",") + " k" + unit
    return ("%g" % v).replace(".", ",") + " " + unit

S = Sheet(70, 42, scale=0.36)
sx = S.text

# ---------------- Encabezado --------------------------------------------------------
sx(2, 40.6, "uPMU prototipo — Hoja 1/2: front-end analógico (1 canal de tensión + 1 canal de corriente)",
   size=15, ha="left", weight="bold")
sx(2, 39.3, "Colombia 60 Hz / 120 V  ·  Chile 50 Hz / 220 V  ·  ADC interno de 12 bit del STM32F303K8 (VDDA = 3,3 V, ratiométrico)  ·  valores = sim/params.py",
   size=10, ha="left", color=NOTE)

S.box(2, 32.9, 33.3, 5.5, fc="#f4f7fb", ec="#9db3cc", lw=1.0)
sx(2.6, 37.5, "Niveles en el pin del ADC (centro = 1,65 V, rango útil ±1,65 V)", size=10, ha="left", weight="bold")
sx(2.6, 35.0,
   "Canal V:  120 V → %.2f V pico (120 %% → %.2f V)   |   220 V → %.2f V pico (120 %% → %.2f V)\n"
   "Canal I:  35 A rms nominal → %.2f V pico (200 %% = 70 A → %.2f V)   [SCT-013-000: 100 A máx.]\n"
   "Filtro RC de ambos canales: R total = %.2f kΩ, C = 10 nF → fc = %.2f kHz, fase a 60 Hz = %.2f° (igual en V e I)\n"
   "Con el desfase de los transformadores, la fase total en el pin es −0,13° (V) y +0,02° (I) a 60 Hz" % (
       P.v_nominal_pk_adc("Colombia"), 1.2 * P.v_nominal_pk_adc("Colombia"),
       P.v_nominal_pk_adc("Chile"), 1.2 * P.v_nominal_pk_adc("Chile"),
       P.i_nominal_pk_adc("Colombia"), 2 * P.i_nominal_pk_adc("Colombia"),
       (P.RB_V + P.RF_V) / 1e3, 1 / (2 * np.pi * (P.RB_V + P.RF_V) * P.C_F) / 1e3,
       np.degrees(np.arctan(60 * 2 * np.pi * (P.RB_V + P.RF_V) * P.C_F))),
   size=10.2, ha="left")

S.box(36.5, 32.9, 31.5, 5.5, fc="#fff8ec", ec="#d9b36c", lw=1.0)
sx(37.1, 37.5, "Reglas de diseño que se verificaron por simulación", size=10, ha="left", weight="bold")
sx(37.1, 35.0,
   "1. Rbv + Rfv = Rbi + Rfi → los dos filtros RC quedan iguales y su fase se cancela.\n"
   "    OJO: la fase V–I NO queda en cero; la de los transformadores no se cancela\n"
   "    (−0,14° a 60 Hz, −0,17° a 50 Hz).  Ver la hoja 3/3 y RESULTADOS_LTspice.\n"
   "2. El capacitor del filtro regresa a VCM, no a GND: su corriente no pasa por la\n"
   "    impedancia de VCM (con GND hubo acople V↔I de ~2 mV, 2,5 LSB, en SPICE).\n"
   "3. El burden Rbi queda siempre conectado: nunca dejar abierto el secundario del SCT013.\n"
   "4. JP1 cerrado = 120 V (Colombia), abierto = 220 V (Chile).   SW1: MAINS / BENCH.",
   size=9.4, ha="left")

# ---------------- Canal de tensión ---------------------------------------------------
YV, YB, YN, YR = 26.0, 23.2, 20.0, 17.0

sx(2, 31.5, "CANAL DE TENSIÓN  (lado red → ZMPT101B 2 mA : 2 mA → burden → filtro → ADC)", size=10.5, ha="left", weight="bold", color="#8a1c1c")
S.terminal(3, YV, "L (J1)", ha="right")
S.terminal(3, YN, "N (J1)", ha="right")

S.fuse((3.26, YV), (8.0, YV), "F1  100 mA T, 250 VAC", side=1, off=0.95)
S.res((8.0, YV), (14.0, YV), "Rp1  %s  2 W  1 %%" % k(P.RP1), side=1, off=0.95, body=2.6)
S.dot(14, YV)
# JP1 puente sobre Rp2
S.wire((14, YV), (14, 28.0)); S.wire((20, YV), (20, 28.0)); S.dot(20, YV)
S.wire((14, 28.0), (16.2, 28.0)); S.wire((17.8, 28.0), (20, 28.0))
S.wire((16.2, 28.0), (17.6, 28.7), lw=1.6)
S.dot(16.2, 28.0, 0.12); S.dot(17.8, 28.0, 0.12)
sx(17, 29.2, "JP1  (cerrado = 120 V)", size=9.4, ha="center")
sx(21.4, 29.2, "Rp total = 62 kΩ (Colombia)  /  118 kΩ (Chile)", size=9.4, ha="left")
S.res((14.0, YV), (20.0, YV), "Rp2  %s  1 W  1 %%" % k(P.RP2), side=-1, off=0.95, body=2.6)

# SW1 (SPDT) MAINS / BENCH
S.wire((20, YV), (22.2, YV))
S.ax.add_patch(Circle((22.2, YV), 0.2, fc="white", ec=INK, lw=1.5, zorder=4))
S.ax.add_patch(Circle((22.2, YB), 0.2, fc="white", ec=INK, lw=1.5, zorder=4))
S.dot(25.2, 24.7, 0.2)
S.wire((25.2, 24.7), (22.7, 25.75), lw=2.0)
S.wire((25.2, 24.7), (26.8, 24.7), (26.8, YV), (28.4, YV))
sx(23.6, 22.0, "SW1\nMAINS ↑ / BENCH ↓", size=8.6, color="#8a1c1c", weight="bold")
S.terminal(3, YB, "")
sx(2.4, YB + 0.95, "J2 GEN (BNC)", size=9, ha="left", weight="bold")
S.wire((3.26, YB), (8, YB))
S.res((8, YB), (14, YB), "R_B  %s" % k(P.R_BENCH), side=-1, off=0.95, body=2.2)
S.wire((14, YB), (22.0, YB))
S.netlabel(15.0, YB + 0.6, "GEN", ha="left", dx=0)

# N: retorno del primario
S.wire((3.26, YN), (28.4, YN))
# T1
S.coil(28.4, YV, loops=4, d=1.0, bulge=+1)
S.coil(31.4, YV, loops=4, d=1.0, bulge=-1)
S.wire((29.9, 26.0), (29.9, 22.0), lw=1.6); S.wire((30.2, 26.0), (30.2, 22.0), lw=1.6)
S.wire((28.4, 22.0), (28.4, YN))
S.wire((31.4, YV), (34.0, YV)); S.dot(34, YV)
S.wire((31.4, 22.0), (31.4, YR)); S.dot(31.4, YR)
sx(24.0, 18.6, "T1  ZMPT101B\n2 mA : 2 mA  (1:1)\naislamiento galvánico", size=8.8, color=INK)

# burden Rbv, filtro Rfv-Cfv, Rs y clamp
S.res((34, YV), (34, YR), "Rbv  %s  1 %%" % k(P.RB_V), side=1, off=0.9, body=2.2)
S.dot(34, YR)
S.res((34, YV), (39.5, YV), "Rfv  %s  1 %%" % k(P.RF_V), side=1, off=0.95, body=2.2)
S.wire((39.5, YV), (41.5, YV)); S.dot(41.5, YV)
S.cap((41.5, YV), (41.5, YR), "Cfv  10 nF  C0G/PP 2 %", side=1, off=0.75)
S.dot(41.5, YR)
S.res((41.5, YV), (46.0, YV), "Rsv  1 kΩ", side=1, off=0.95, body=2.0)
S.wire((46, YV), (47.5, YV)); S.dot(47.5, YV)
S.diode((47.5, YV), (47.5, 29.6), "D1v\n1N4148", side=-1, off=0.8)
S.rail_flag(47.5, 30.9, "+3V3A")
S.diode((47.5, 22.4), (47.5, YV), "D2v", side=-1, off=0.8)
S.ground(47.5, 22.4)
S.wire((47.5, YV), (55, YV))
S.netlabel(49.0, YV + 0.35, "ADC_V", ha="left", dx=0)

# ---------------- Canal de corriente -------------------------------------------------
YI = 9.0
sx(19.5, 15.8, "CANAL DE CORRIENTE  (SCT-013-000 → burden → filtro → ADC)", size=10.5, ha="left", weight="bold", color="#8a1c1c")
sx(2.2, 12.4, "SCT-013-000  CONFIRMAR\n100 A : 50 mA\n(2000 : 1)\nJ4 jack 3,5 mm\n(punta ↔ manga)", size=8.8, ha="left")
S.coil(6.0, 14.4, loops=4, d=1.0, bulge=+1)
S.wire((6.0, 14.4), (6.0, YR)); S.dot(6.0, YR)
S.wire((6.0, 10.4), (6.0, YI), (11.0, YI))
S.wire((7.6, 14.4), (7.6, 10.4), lw=1.6); S.wire((7.9, 14.4), (7.9, 10.4), lw=1.6)
S.dot(11, YI)
S.res((11, YI), (11, YR), "Rbi  %s  1 %%" % k(P.RB_I), side=-1, off=0.9, body=2.2)
S.dot(11, YR)
S.res((11, YI), (16.5, YI), "Rfi  %s  1 %%" % k(P.RF_I), side=1, off=0.95, body=2.2)
S.wire((16.5, YI), (18.0, YI)); S.dot(18.0, YI)
S.cap((18.0, YI), (18.0, YR), "Cfi  10 nF  C0G/PP 2 %", side=-1, off=0.75)
S.dot(18.0, YR)
S.res((18.0, YI), (23.5, YI), "Rsi  1 kΩ", side=1, off=0.95, body=2.0)
S.wire((23.5, YI), (25, YI)); S.dot(25, YI)
S.diode((25, YI), (25, 12.6), "D1i\n1N4148", side=-1, off=0.8)
S.rail_flag(25, 13.9, "+3V3A")
S.diode((25, 5.5), (25, YI), "D2i", side=-1, off=0.8)
S.ground(25, 5.5)
S.wire((25, YI), (55, YI))
S.netlabel(40.0, YI + 0.35, "ADC_I", ha="left", dx=0)

# banco corriente: GEN -> R_BI -> JP4 -> nodo bi
S.netlabel(2.4, 5.2, "GEN", ha="left", dx=0, dy=0.9)
S.wire((2.4, 5.2), (4.5, 5.2))
S.res((4.5, 5.2), (9.0, 5.2), "R_BI  %s" % k(P.R_BENCH), side=-1, off=0.95, body=2.0)
S.wire((9.0, 5.2), (11.0, 5.2), (11.0, 6.3))
S.wire((11.0, 8.1), (11.0, YI))
S.wire((11.0, 6.3), (11.7, 8.0), lw=1.8)
S.dot(11, 6.3, 0.12)
sx(12.3, 7.2, "JP4 (banco; abierto en uso real)", size=8.6, ha="left", color="#8a1c1c", weight="bold")

# ---------------- Riel VCM ------------------------------------------------------------
S.wire((6.0, YR), (41.5, YR), lw=2.2, color=NET)
S.netlabel(6.4, YR + 0.5, "VCM  1,65 V  — referencia común de los dos canales (retorno de burden y filtros)", ha="left", dx=0, size=9.4)

# ---------------- Bloque VCM -------------------------------------------------------
sx(34.5, 6.9, "Bloque de punto medio (VCM = VDDA/2)", size=9.8, ha="left", weight="bold", color="#8a1c1c")
S.rail_flag(32, 7.2, "+3V3A")
S.res((32, 7.2), (32, 4.4), "R_A  10 kΩ  0,1 %", side=-1, off=0.9, body=1.6)
S.dot(32, 4.4)
S.res((32, 4.4), (32, 1.6), "R_B2  10 kΩ  0,1 %", side=-1, off=0.9, body=1.6)
S.ground(32, 1.6)
S.wire((32, 4.4), (45.5, 4.4))
S.cap((36.5, 4.4), (36.5, 1.6), "C_V1  10 µF", side=-1, off=0.8)
S.dot(36.5, 4.4); S.ground(36.5, 1.6)
S.cap((40.5, 4.4), (40.5, 1.6), "C_V2  100 nF", side=-1, off=0.8)
S.dot(40.5, 4.4); S.ground(40.5, 1.6)
S.terminal(45.5, 4.4, "")
sx(46.2, 5.4, "TP_VCM", size=8.6, ha="left", color=NOTE)
S.netlabel(46.4, 4.0, "VCM", ha="left", dx=0, size=9.4)

# ---------------- MCU ------------------------------------------------------------
S.box(55, 6.0, 12.5, 25.5, fc="#eef6ee", ec="#4a7a4a", lw=2.0)
sx(61.25, 29.5, "NUCLEO-F303K8", size=11, weight="bold")
sx(61.25, 28.3, "STM32F303K8T6", size=9.5)
sx(61.25, 24.1, "PA0 / A0\nADC1_IN1", size=9, weight="bold")
sx(61.25, 15.6, "ADC1 + ADC2\nmodo dual simultáneo\n12 bit · TIM2 TRGO\n60 kS/s (hoja 2)", size=8.6, color=NOTE)
sx(61.25, 7.5, "PA4 / A3\nADC2_IN1", size=9, weight="bold")
S.terminal(55, YV, "")
S.terminal(55, YI, "")

sx(2, 1.0, "Verificar la asignación de pines contra UM1956 (pinout del Nucleo-32) antes de cablear.  Esquemático de referencia: no incluye PCB ni lista final de compra.",
   size=8.4, ha="left", color=NOTE, style="italic")

S.save("uPMU_AFE_hoja1_analogico")
print("hoja 1 lista")
