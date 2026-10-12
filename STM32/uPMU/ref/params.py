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
C_ADC_PAR = 5e-12     # capacitancia parásita del pin (modelo)

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
