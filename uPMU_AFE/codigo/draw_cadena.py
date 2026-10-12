# -*- coding: utf-8 -*-
"""Diagrama de bloques de la cadena de medición (figura del README).

Convención: cada bloque es un COMPONENTE y cada flecha lleva la SEÑAL que pasa
por ella, con su magnitud y su unidad.

Las cifras del front-end salen de params.py; las del firmware están en
STM32/uPMU/docs/RESULTADOS.md y FORMATO_TRAMA.md.

    python draw_cadena.py     ->  figuras/cadena_medicion.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

import numpy as np

import params as P
from rutas import FIGURAS

TINTA = "#000000"
SENAL = "#2b2b2b"

fig, ax = plt.subplots(figsize=(17.6, 8.6))
ax.set_xlim(-7.6, 41.8)
ax.set_ylim(-1.6, 22.6)
ax.set_aspect("equal")
ax.axis("off")

W, H = 4.6, 2.3
COL = [0.0, 7.2, 14.4, 21.6, 28.8]
XADC = 36.2


def c(t):
    """Coma decimal (solo para cifras)."""
    return t.replace(".", ",")


def bloque(x, y, titulo, w=W, h=H, fs=9.0):
    ax.add_patch(Rectangle((x, y), w, h, fc="white", ec=TINTA, lw=1.1, zorder=2))
    ax.text(x + w / 2, y + h / 2, titulo, ha="center", va="center", fontsize=fs,
            color=TINTA, zorder=3, linespacing=1.45)
    return (x, y, w, h)


def der(b, f=0.5):
    x, y, w, h = b
    return (x + w, y + h * f)


def izq(b, f=0.5):
    x, y, w, h = b
    return (x, y + h * f)


def arr(b):
    x, y, w, h = b
    return (x + w / 2, y + h)


def aba(b):
    x, y, w, h = b
    return (x + w / 2, y)


def flecha(p, q, texto="", dy=0.5, fs=7.6, lab=None, ha="center"):
    """Flecha recta con el nombre de la señal encima."""
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=12,
                                 lw=1.1, color=TINTA, zorder=4, shrinkA=0, shrinkB=0))
    if texto:
        lx, ly = lab if lab else ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + dy)
        ax.text(lx, ly, texto, ha=ha, va="center", fontsize=fs, color=SENAL,
                zorder=5, linespacing=1.3)


def ruta(puntos, texto="", lab=None, fs=7.6, ha="left"):
    """Conexión en L: tramos rectos y punta de flecha solo al final."""
    for a, b in zip(puntos[:-1], puntos[1:]):
        estilo = "-|>" if b is puntos[-1] else "-"
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle=estilo, mutation_scale=12,
                                     lw=1.1, color=TINTA, zorder=4,
                                     shrinkA=0, shrinkB=0))
    if texto and lab:
        ax.text(lab[0], lab[1], texto, ha=ha, va="center", fontsize=fs,
                color=SENAL, zorder=5, linespacing=1.3)


g = P.GRIDS["Colombia"]
i_pri = g["Vrms"] / g["Rp"] * 1e3
v_bur = g["Vrms"] / g["Rp"] * P.RB_V
i_sec = g["In_rms"] / P.CT_RATIO * 1e3
i_bur = g["In_rms"] / P.CT_RATIO * P.RB_I
fcv = 1 / (2 * np.pi * (P.RB_V + P.RF_V) * P.C_F) / 1e3

# ================================ título =====================================
ax.text(-7.6, 21.8, "uPMU — cadena de medición", fontsize=15, weight="bold",
        ha="left", color=TINTA)
ax.text(-7.6, 21.0,
        "Cada bloque es un componente; cada flecha, la señal que lo recorre.   "
        "Valores nominales para Colombia: 120 V, 60 Hz, 35 A.",
        fontsize=8.8, ha="left", color=SENAL)

# ========================= canal de tensión ==================================
YV = 17.0
rp = bloque(COL[0], YV, "Fusible F1  +  Rp\n%s kΩ" % c("%g" % (g["Rp"] / 1e3)))
zmpt = bloque(COL[1], YV, "Transformador\nZMPT101B\n2 mA : 2 mA")
rbv = bloque(COL[2], YV, "Burden\nRbv %s Ω" % c("%g" % P.RB_V))
rcv = bloque(COL[3], YV, "Filtro RC anti-aliasing\nfc = %s kHz" % c("%.2f" % fcv))
prv = bloque(COL[4], YV, "Rs %s kΩ  +\n2 × 1N4148" % c("%g" % (P.RS_ADC / 1e3)))

flecha((COL[0] - 5.2, YV + H / 2), izq(rp),
       c("Tensión de red\n%g V rms,  %g Hz" % (g["Vrms"], g["f0"])), dy=0.95)
flecha(der(rp), izq(zmpt), c("%.2f mA rms" % i_pri))
flecha(der(zmpt), izq(rbv), c("%.2f mA rms\n(aislado)" % i_pri), dy=0.78)
flecha(der(rbv), izq(rcv), c("%.2f V rms" % v_bur))
flecha(der(rcv), izq(prv), c("%.2f V rms" % v_bur))

# ========================= canal de corriente ================================
YI = 13.2
sct = bloque(COL[1], YI, "Transformador\nSCT-013\n2000 : 1")
rbi = bloque(COL[2], YI, "Burden\nRbi %s Ω" % c("%g" % P.RB_I))
rci = bloque(COL[3], YI, "Filtro RC anti-aliasing\nfc = %s kHz" % c("%.2f" % fcv))
pri = bloque(COL[4], YI, "Rs %s kΩ  +\n2 × 1N4148" % c("%g" % (P.RS_ADC / 1e3)))

flecha((COL[1] - 5.2, YI + H / 2), izq(sct),
       c("Corriente de línea\n%g A rms" % g["In_rms"]), dy=0.95)
flecha(der(sct), izq(rbi), c("%.1f mA rms" % i_sec))
flecha(der(rbi), izq(rci), c("%.2f V rms" % i_bur))
flecha(der(rci), izq(pri), c("%.2f V rms" % i_bur))

# ============================== ADC ==========================================
adc = bloque(XADC, YI, "ADC de 12 bit\nADC1 + ADC2\nsimultáneos\n(PA0, PA4)",
             h=YV + H - YI)
flecha(der(prv), izq(adc, 0.80), c("0,36 – 2,94 V"), dy=0.5)
flecha(der(pri), izq(adc, 0.20), c("0,91 – 2,39 V"), dy=0.5)

# referencia de nivel medio
vcm = bloque(COL[2], 9.3, "Divisor VCM\n2 × %s kΩ" % c("%g" % (P.R_VCM / 1e3)), h=1.9)
flecha(arr(vcm), aba(rbi), "")
ax.text(COL[2] + W / 2 + 0.35, (9.3 + 1.9 + YI) / 2,
        c("%.2f V  (nivel medio,\ncomún a los dos canales)" % P.VCM),
        fontsize=7.6, ha="left", va="center", color=SENAL, linespacing=1.3)
flecha((COL[2] - 4.2, 9.3 + 0.95), izq(vcm), c("VDDA = %.1f V" % P.VDDA), dy=0.5)

# ========================= cadena digital ====================================
YD = 6.0
cic = bloque(COL[4], YD, "Filtro CIC\norden 3,  R = 4")
ven = bloque(COL[3], YD, "Ventana\nde 4 ciclos")
est = bloque(COL[2], YD, "Estimador\nIpDFT (Hann) +\nmínimos cuadrados")
tra = bloque(COL[1], YD, "Empaquetado\nde la trama")
pc = bloque(COL[0], YD, "PC\n(visor / registro)")

ruta([aba(adc), (XADC + W / 2, YD + H / 2), der(cic)],
     c("códigos de 12 bit\n%g kS/s" % (P.FS / 1e3)),
     lab=(XADC + W / 2 + 0.4, (YI + YD + H) / 2))
flecha(izq(cic), der(ven), c("%g kS/s" % (P.FS / P.DECIM / 1e3)))
flecha(izq(ven), der(est), c("1000 / 1200\nmuestras"), dy=0.78)
flecha(izq(est), der(tra), c("f,  V∠,  I∠"))
flecha(izq(tra), der(pc), c("115200 baud\n30 o 25 tramas/s"), dy=0.78)

ax.text(COL[4] + W / 2, YD - 0.7, c("1 LSB = %.3f mV" % (1e3 * P.LSB)),
        fontsize=7.6, ha="center", color=SENAL)

# ========================= sincronización ====================================
gps = bloque(COL[4], 0.3, "Receptor GPS\nNEO-7M", h=4.4)
cap = bloque(COL[3], 2.8, "Captura del PPS\nTIM2_CH2 + TIM3", h=1.9)
nme = bloque(COL[3], 0.3, "Decodificador NMEA\n(GGA, RMC)", h=1.9)
sel = bloque(COL[2], 0.3, "Sello de tiempo\nUTC", h=4.4)

flecha((COL[4], 3.75), der(cap), "PPS,  1 Hz", dy=0.5)
flecha((COL[4], 1.25), der(nme), "NMEA", dy=0.5)
flecha(izq(cap), (COL[2] + W, 3.75), "n.º de muestra", dy=0.5)
flecha(izq(nme), (COL[2] + W, 1.25), c("fecha y hora UTC"), dy=0.5)
ruta([izq(sel), (COL[1] + W / 2, 2.5), aba(tra)],
     c("sello UTC  +  bandera\nSYNC / HOLD / NOSYNC"),
     lab=(COL[1] + W / 2 + 0.4, (2.5 + YD) / 2))

# ================================ pie ========================================
ax.text(-7.6, -1.25,
        "Cifras del front-end: codigo/params.py.   Cifras del firmware: "
        "STM32/uPMU/docs/RESULTADOS.md.   Figura generada por codigo/draw_cadena.py.",
        fontsize=7.6, ha="left", color="#777777", style="italic")

fig.tight_layout(pad=0.4)
fig.savefig(FIGURAS / "cadena_medicion.png", dpi=150, facecolor="white")
plt.close(fig)
print("cadena_medicion.png lista")
