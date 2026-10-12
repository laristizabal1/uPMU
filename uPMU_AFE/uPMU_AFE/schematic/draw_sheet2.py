"""Hoja 2/2 - MCU, GPS (PPS + NMEA), selector 50/60 Hz y enlace de datos."""
from schlib import *

S = Sheet(70, 42, scale=0.36)
sx = S.text

sx(2, 40.6, "uPMU prototipo — Hoja 2/2: MCU, sincronización GPS y selector de país", size=15, ha="left", weight="bold")
sx(2, 39.3, "NUCLEO-F303K8 (STM32F303K8T6, Cortex-M4F, 72 MHz)  ·  GPS con PPS  ·  los nombres de red (ADC_V, ADC_I, +3V3A) vienen de la hoja 1",
   size=10, ha="left", color=NOTE)

# ---------------- MCU ---------------------------------------------------------------
BX, BY, BW, BH = 24, 10, 22, 24
S.box(BX, BY, BW, BH, fc="#eef6ee", ec="#4a7a4a", lw=2.0)
sx(BX + BW / 2, BY + BH - 1.2, "NUCLEO-F303K8", size=12, weight="bold")
sx(BX + BW / 2, BY + BH - 2.4, "STM32F303K8T6", size=10)
sx(BX + BW / 2, BY + 11.2,
   "TIM2 (32 bit, 72 MHz)\nARR = 1199 → TRGO a 60 kHz\n→ ADC1 + ADC2 simultáneos\n→ DMA circular\n\nTIM2_CH2: captura del PPS\n(mismo contador que el ADC)",
   size=9.2, color=NOTE)


def pin_left(y, label, net=None, color=INK, extra=None):
    S.terminal(BX, y, "")
    S.wire((BX - 0.26, y), (BX - 6.5, y))
    sx(BX + 0.6, y, label, size=9.4, ha="left", weight="bold")
    if net:
        S.netlabel(BX - 6.5, y + 0.55, net, ha="left", dx=0, size=9.6)


def pin_right(y, label, net=None):
    S.terminal(BX + BW, y, "")
    sx(BX + BW - 0.6, y, label, size=9.4, ha="right", weight="bold")


# izquierda: entradas analogicas y alimentacion
pin_left(29.0, "PA0 / A0  (ADC1_IN1)", "ADC_V")
pin_left(26.0, "PA4 / A3  (ADC2_IN1)", "ADC_I")
S.rail_flag(BX - 6.5, 21.9, "+3V3A")
S.wire((BX - 6.5, 21.4), (BX - 6.5, 20.0), (BX - 0.26, 20.0))
S.terminal(BX, 20.0, "")
sx(BX + 0.6, 20.0, "3V3", size=9.4, ha="left", weight="bold")
S.wire((BX - 6.5, 17.2), (BX - 0.26, 17.2)); S.terminal(BX, 17.2, "")
S.ground(BX - 6.5, 17.2)
sx(BX + 0.6, 17.2, "GND", size=9.4, ha="left", weight="bold")
sx(BX - 6.9, 23.2, "VDDA = 3V3 del Nucleo\n(verificar filtrado en UM1956)", size=8.4, ha="right", color=NOTE)

# derecha: GPS
GX, GY, GW, GH = 56, 15.5, 12, 15
S.box(GX, GY, GW, GH, fc="#f4f0fa", ec="#6a5a99", lw=2.0)
sx(GX + GW / 2, GY + GH - 1.0, "Módulo GPS", size=11, weight="bold")
sx(GX + GW / 2, GY + GH - 2.3, "NEO-6M / NEO-M8N\n(GY-GPS6MV2)", size=9.2)
S.terminal(GX + GW / 2, GY + GH + 0.26, "")
sx(GX + GW / 2, GY + GH + 1.2, "ANT (SMA, antena activa\na la ventana)", size=8.8)
pins = [(27.0, "PPS", "PA1 / A1  (TIM2_CH2)", "PPS"), (24.0, "TX", "PA10 / D0  (USART1_RX)", "NMEA →"),
        (21.0, "RX", "PA9 / D1  (USART1_TX)", "← cfg"), (19.0, "VCC", "3V3", ""), (17.0, "GND", "GND", "")]
for y, gp, mp, tag in pins:
    S.terminal(BX + BW, y, "")
    sx(BX + BW - 0.6, y, mp, size=9.4, ha="right", weight="bold")
    S.wire((BX + BW + 0.26, y), (GX - 0.26, y))
    S.terminal(GX, y, "")
    sx(GX + 0.6, y, gp, size=9.4, ha="left", weight="bold")
    if tag:
        sx((BX + BW + GX) / 2, y + 0.55, {"PPS": "PPS", "TX": "GPS_TX (NMEA)", "RX": "GPS_RX"}[gp], size=9, color=NET, weight="bold")
S.wire((BX + BW + 0.26, 19.0), (BX + BW + 2.0, 19.0))   # etiquetas de alimentacion
sx((BX + BW + GX) / 2, 19.55, "+3V3 (GPS)", size=9, color="#b00020", weight="bold")
sx((BX + BW + GX) / 2, 17.55, "GND", size=9, color=NET, weight="bold")

# abajo: selector 50/60 y LED
S.terminal(32, BY, "")
sx(32, BY + 0.9, "PB0 / D3", size=9.4, weight="bold")
S.wire((32, BY - 0.26), (32, 6.6))
S.dot(32, 6.6, 0.12)
S.wire((32, 6.6), (32.9, 5.2), lw=1.8)
S.wire((32, 4.6), (32, 4.0)); S.ground(32, 4.0)
S.dot(32, 4.8, 0.12)
sx(31.0, 6.6, "SW3  50/60 Hz\nabierto = 60 Hz (CO)\ncerrado a GND = 50 Hz (CL)\n(pull-up interno)", size=8.8, ha="right")
S.terminal(40, BY, "")
sx(40, BY + 0.9, "PB3 / D13", size=9.4, weight="bold")
S.wire((40, BY - 0.26), (40, 7.4))
S.res((40, 7.4), (40, 4.4), "R_L  470 Ω", side=1, off=0.9, body=1.6)
S.diode((40, 4.4), (40, 2.6), "LD3 (en placa)", side=-1, off=0.9, size=0.7)
S.ground(40, 2.6)
sx(41.0, 3.2, "LED de estado\n(PPS válido)", size=8.8, ha="left", color=NOTE)

# arriba: USB / VCP
S.terminal(BX + 11, BY + BH, "")
S.wire((BX + 11, BY + BH + 0.26), (BX + 11, BY + BH + 2.4))
S.box(BX + 5.5, BY + BH + 2.4, 11, 2.2, fc="white", ec=INK, lw=1.6)
sx(BX + 11, BY + BH + 3.5, "USB micro (ST-LINK VCP)", size=9.2, weight="bold")
sx(BX + 11.6, BY + BH + 1.2, "USART2 · PA2 / PA15", size=8.6, ha="left", color=NOTE)
sx(BX + 11, BY + BH + 5.4, "→ PC / ESP32-S3: tramas de fasores", size=8.8, color=NOTE)

# ---------------- Notas ------------------------------------------------------------
S.box(2, 1.2, 19.5, 7.6, fc="#fff8ec", ec="#d9b36c", lw=1.0)
sx(2.6, 8.0, "Plan de temporización (confirmar en RM0316)", size=9.6, ha="left", weight="bold")
sx(2.6, 4.7,
   "· Reloj: HSE 8 MHz del MCO del ST-LINK → PLL 72 MHz\n"
   "  (el Nucleo-32 no trae cristal).\n"
   "· Fs = 60 kS/s en 50 y 60 Hz → ventana de 4 ciclos:\n"
   "  4000 muestras (60 Hz) o 4800 (50 Hz).\n"
   "· Tiempo de muestreo del ADC ≥ 7,5 ciclos (Rs = 1 kΩ).",
   size=8.6, ha="left")
S.box(48, 1.2, 20, 11.5, fc="#f4f7fb", ec="#9db3cc", lw=1.0)
sx(48.6, 11.9, "Cadena de procesamiento (simulada, hoja 1 + este MCU)", size=9.6, ha="left", weight="bold")
sx(48.6, 7.2,
   "1. Captura del PPS → mide fase muestra-PPS y periodo real\n"
   "    (corrige deriva del cristal).\n"
   "2. CIC3, R = 4: 60 → 15 kS/s (retardo 4,5 muestras fijo).\n"
   "3. IpDFT con ventana Hann + ajuste sinusoidal (Gauss-\n"
   "    Newton) sobre 4 ciclos → f, módulo y ángulo.\n"
   "4. Compensa RC y CIC con el modelo; calibración de\n"
   "    1 punto por canal con carga resistiva.\n"
   "5. Sin PPS: bandera «no sincronizado» (nunca válido).",
   size=8.6, ha="left")

S.save("uPMU_AFE_hoja2_mcu_gps")
print("hoja 2 lista")
