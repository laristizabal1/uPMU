"""Valores de componentes del front-end uPMU (1 canal V + 1 canal I).

Fuente única: de aquí salen el netlist SPICE, la simulación en Python y las
anotaciones del esquemático.  Cambiar un valor aquí y regenerar todo.
"""
import numpy as np

# --- Alimentación / ADC -------------------------------------------------
VDDA = 3.3            # V, referencia del ADC (ratiométrico)
NBITS = 12
LSB = VDDA / 2**NBITS # 0.806 mV
VCM = VDDA / 2        # 1.65 V

# --- Canal de tensión: ZMPT101B 2 mA : 2 mA (relación 1:1) -------------------
RP1 = 62e3            # 2 W  -> solo (Colombia, 120 V): I = 120/62k = 1.94 mA
RP2 = 56e3            # 1 W  -> en serie para Chile (220 V): 220/118k = 1.86 mA
RB_V = 470.0          # carga (burden) del secundario: 2 mA rms -> 0.94 V rms
RF_V = 3.30e3         # R del filtro anti-aliasing
C_F = 10e-9           # C del filtro (film PP / C0G) -> fc ~ 4.2 kHz con RB+RF
R_BENCH = 2.2e3       # banco: generador 4.4 Vrms -> 2 mA

# --- Canal de corriente: SCT013-100 (100 A : 50 mA = 2000:1) -------------------
CT_RATIO = 2000.0
RB_I = 30.0           # burden: 35 A rms nominal -> 0.74 V pico (200% -> 1.48 V)
# Para igualar la constante de tiempo con el canal V (fase V-I se cancela):
# RB_V + RF_V = RB_I + RF_I  ->  RF_I = RB_V + RF_V - RB_I  (E96: 3.74 k)
RF_I = 3.74e3

# --- Protección / entrada ADC -------------------------------------------
RS_ADC = 1e3          # serie antes del pin
# CONFIRMAR (hoja de datos STM32F303, «ADC characteristics», nota del diagrama
# de conexión típica): C_parásita = pad + PCB ≈ 7 pF.  Antes estaba en 5 pF.
C_ADC_PAR = 7e-12
# Red de muestreo del ADC.  CONFIRMAR: la hoja del F303 no publica R_ADC ni
# C_ADC; se toman los valores de AN2834 (ejemplo con R_ADCmax = 1 kΩ) y los
# 5 pF que ST reporta para F4/G4 en sus notas y en el foro.
R_ADC = 1e3           # Ω, resistencia del interruptor de muestreo
C_ADC_SH = 5e-12      # F, condensador de muestreo y retención
# Medido en el firmware (STM32/uPMU/docs/RESULTADOS.md, T3.1/T3.2):
# reloj del ADC = AHB/4 = 15 MHz y tiempo de muestreo = 61,5 ciclos.
F_ADC_CLK = 15e6
T_SAMPLE = 61.5 / F_ADC_CLK   # 4,10 µs

# --- Modelo del transformador de corriente (antes: ideal) -----------------
# Modelo referido al secundario: fuente ideal Ip/N en paralelo con Lm, y Rw en
# serie.  El error de fase (adelanto) vale  eps = (Rw + Rcarga) / (ω·Lm)  rad.
# Lm no se inventa: se DERIVA del error de fase de la hoja de datos.

# ZMPT101B (redmine.laas.fr/attachments/download/2519/ZMPT101B.pdf):
# «phase angle error ≤ 20'», medido con 2 mA de entrada y resistencia de
# muestreo de 100 Ω.  OJO: este diseño usa 470 Ω = 4,7× esa carga, así que el
# error de fase real es mayor que 20' (ver sim/RESULTADOS_LTspice.md).
ZMPT_PH_SPEC_MIN = 20.0    # minutos de arco (20' = 0,3333°)
ZMPT_PH_SPEC_RB = 100.0    # Ω, carga del ensayo de la hoja de datos
ZMPT_PH_SPEC_F = 50.0      # Hz. CONFIRMAR: la hoja no indica la frecuencia del ensayo
RW_V = 150.0               # Ω, devanado secundario. CONFIRMAR: medir con óhmetro

# SCT-013: la hoja de YHDC no publica error de fase (CONFIRMAR: medir).
# Se conserva el supuesto que ya usaba simulate_chain.py: 1° con 30 Ω.
SCT_PH_ASSUM_DEG = 1.0
SCT_PH_ASSUM_RB = 30.0
SCT_PH_ASSUM_F = 50.0
RW_I = 20.0                # Ω, devanado secundario. CONFIRMAR: medir con óhmetro

# Resistencia del devanado primario del ZMPT101B: se suma a Rp y solo REDUCE la
# señal, así que 0 es la elección conservadora para el margen contra 3,3 V.
# CONFIRMAR: medir y anotar (mueve la ganancia ~1 %; la calibración la absorbe).
R_PRI_ZMPT = 0.0


def _lm(rw, rb_spec, f_spec, eps_deg):
    """Lm que reproduce un error de fase eps_deg con carga rb_spec a f_spec."""
    return (rw + rb_spec) / (2 * np.pi * f_spec * np.radians(eps_deg))


LM_V = _lm(RW_V, ZMPT_PH_SPEC_RB, ZMPT_PH_SPEC_F, ZMPT_PH_SPEC_MIN / 60.0)
LM_I = _lm(RW_I, SCT_PH_ASSUM_RB, SCT_PH_ASSUM_F, SCT_PH_ASSUM_DEG)


def ct_phase_deg(f, rw, lm, rb):
    """Adelanto de fase del CT [°] con carga rb a la frecuencia f."""
    return np.degrees((rw + rb) / (2 * np.pi * f * lm))


def rc_phase_deg(f, rb, rf):
    """Retardo de fase del filtro RC [°] (negativo)."""
    return -np.degrees(np.arctan(2 * np.pi * f * C_F * (rb + rf)))


# --- Punto medio ----------------------------------------------------------
R_VCM = 10e3          # 2 x 10 kΩ
C_VCM_BULK = 10e-6
C_VCM_HF = 100e-9

# --- Muestreo ------------------------------------------------------------
FS = 60e3             # Hz, disparado por TIM2
DECIM = 4             # CIC3 R=4 -> 15 kS/s
CYCLES = 4            # ventana del estimador

# --- Escenarios de red ---------------------------------------------------
GRIDS = {
    "Colombia": dict(f0=60.0, Vrms=120.0, Rp=RP1, In_rms=35.0),
    "Chile":    dict(f0=50.0, Vrms=220.0, Rp=RP1 + RP2, In_rms=35.0),
}


def v_nominal_pk_adc(grid):
    g = GRIDS[grid]
    return np.sqrt(2) * g["Vrms"] / g["Rp"] * RB_V


def i_nominal_pk_adc(grid):
    g = GRIDS[grid]
    return np.sqrt(2) * g["In_rms"] / CT_RATIO * RB_I


if __name__ == "__main__":
    for g in GRIDS:
        print(g, "V pico nominal ADC = %.3f V (120%% -> %.3f)" % (
            v_nominal_pk_adc(g), 1.2 * v_nominal_pk_adc(g)),
              "| I pico nominal = %.3f V (200%% -> %.3f)" % (
            i_nominal_pk_adc(g), 2 * i_nominal_pk_adc(g)))
    print("fc_V = %.0f Hz, fc_I = %.0f Hz" % (
        1 / (2 * np.pi * (RB_V + RF_V) * C_F), 1 / (2 * np.pi * (RB_I + RF_I) * C_F)))
    print("Lm_V = %.1f H, Lm_I = %.2f H (derivadas de la fase de hoja de datos)" % (LM_V, LM_I))
    for f in (50.0, 60.0):
        pv, pi_ = ct_phase_deg(f, RW_V, LM_V, RB_V), ct_phase_deg(f, RW_I, LM_I, RB_I)
        rc = rc_phase_deg(f, RB_V, RF_V)
        print("  %g Hz: CT_V = +%.3f°, CT_I = +%.3f°, RC = %.3f° -> neto V %.3f°,"
              " I %.3f°, V-I %.3f°" % (f, pv, pi_, rc, pv + rc, pi_ + rc, pv - pi_))
    print("t_muestreo ADC = %.2f µs; tau = (RS_ADC+R_ADC)·C_ADC_SH = %.1f ns;"
          " 12 bits piden %.0f ns -> margen %.0fx" % (
              1e6 * T_SAMPLE, 1e9 * (RS_ADC + R_ADC) * C_ADC_SH,
              1e9 * (RS_ADC + R_ADC) * C_ADC_SH * np.log(2 ** (NBITS + 1)),
              T_SAMPLE / ((RS_ADC + R_ADC) * C_ADC_SH * np.log(2 ** (NBITS + 1)))))
