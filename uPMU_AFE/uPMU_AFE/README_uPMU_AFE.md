# uPMU — front-end (1 V + 1 I): esquemático y simulación

Todo sale de un solo archivo de valores: `sim/params.py`. Si cambias un componente ahí y corres `sim/run_all.sh`, se regeneran netlists, SPICE y la simulación de la cadena.

## 1. Qué hay

| Archivo | Para qué |
|---|---|
| `schematic/uPMU_AFE_hoja1_analogico.png/.pdf` | Hoja 1: canal V, canal I, punto medio VCM, entradas al ADC |
| `schematic/uPMU_AFE_hoja2_mcu_gps.png/.pdf` | Hoja 2: Nucleo-F303K8, GPS (PPS + NMEA), selector 50/60 Hz, USB |
| `sim/uPMU_AFE_LTspice.cir` | Netlist para LTspice (transitorio activo, `.ac` comentado) |
| `sim/uPMU_AFE_ac_{V,I}.cir`, `uPMU_AFE_tran*.cir`, `uPMU_AFE_mc_*.cir` | Los 14 netlists, para LTspice y ngspice (los `mc_` solo LTspice) |
| `sim/simulate_chain.py` | Cadena completa: sensor → RC → ADC 12 bit → CIC3 → IpDFT + ajuste → TVE (Monte Carlo de tolerancias) |
| `sim/run_ltspice.py`, `run_ltspice.bat` | Corre LTspice en batch (`-b`), analiza y grafica |
| `sim/compare_sims.py` | LTspice vs ngspice vs modelo cerrado de Python |
| **`sim/RESULTADOS_LTspice.md`** | **Resultados, correcciones de modelado y cambios propuestos. Empieza por aquí.** |
| `sim/results_*.txt`, `sim/ltspice_*.png` | Resultados y gráficas de la corrida |

## 2. Cómo simularlo

**LTspice (todo, en batch):** `sim
un_ltspice.bat` — regenera netlists, corre los 14 en modo `-b`, analiza y deja los PNG. Probado con LTspice 26.0.2.

**LTspice (a mano):** File → Open → `sim/uPMU_AFE_LTspice.cir` → Run. Graficar `V(adcv)` y `V(adci)` (deben oscilar alrededor de 1,65 V). Para respuesta en frecuencia, comentar `.tran` y descomentar `.ac`. Los `reltol=1e-6` del netlist son necesarios: con el valor por defecto el solver deja ~2 mV de error numérico (2,5 LSB).
Para cambiar de país: en `.param` cambiar `Vpk`, `freq` y el valor de `Rp` (62 k Colombia, 118 k Chile). Para otro nivel de carga, escalar `Vpk` e `Ipk`.

**Ojo con el transitorio:** el magnetizante de los transformadores tarda en asentarse (τ hasta 0,44 s, más una resonancia de 4–17 Hz con los 10 µF de VCM). Los netlists simulan 5 s y guardan los últimos 100 ms. Si acortas eso, los picos salen falseados.

**Python (sin instalar nada raro):** `cd sim && python3 simulate_chain.py` (usa numpy). `./run_all.sh` además corre ngspice vía node (`npm install eecircuit-engine` en `ngspice_runner/`).

## 3. Cómo armarlo (orden recomendado, de menor a mayor riesgo)

1. **Solo baja tensión, sin red.** Armar el bloque VCM (2×10 kΩ + 10 µF + 100 nF) y medir 1,65 V en TP_VCM. Con el Nucleo conectado debe seguir en 1,65 V ± pocos mV.
2. **Canal I con generador (SW/JP4 en banco).** Sin conectar el SCT013, generador sinusoidal ~4,4 Vrms a 60 Hz por R_BI 2,2 kΩ → ≈2 mA rms en Rbi (30 Ω): debe verse ≈60 mV rms sobre 1,65 V en ADC_I. Es la prueba del filtro, el ADC y el firmware.
3. **Canal V con generador (SW1 en BENCH).** Mismo generador por R_B 2,2 kΩ al primario del ZMPT101B: 2 mA rms → ≈0,94 V rms (1,33 V pico) en ADC_V. Con el mismo generador en ambos canales, el ángulo V–I medido debe ser ≈0°: lo que quede es el desfase propio del hardware y el firmware, y se resta.
4. **Calibración de fase/ganancia de 1 punto por canal** con una carga resistiva sobre la red (corriente en fase con la tensión). Sin este paso el TVE simulado es 2,1–2,7 %.
5. **Red real solo después**, a través de un transformador de aislamiento, con el circuito de red (L, N, F1, Rp, primario del T1) dentro de una caja cerrada y fusible puesto. SW1 en MAINS, JP4 abierto, JP1 según el país.

Reglas del circuito: el burden Rbi no se desconecta nunca (secundario del SCT013 abierto = tensión peligrosa); los capacitores del filtro regresan a VCM, no a GND; Rbv + Rfv = Rbi + Rfi para que la fase de los dos RC se cancele.

## 4. Lista del front-end

| Ref. | Valor | Nota |
|---|---|---|
| T1 | ZMPT101B 2 mA : 2 mA | el **transformador solo**, no el módulo con amplificadores (ese tiene decenas de grados de error de fase). Medir la resistencia DC del primario (suma a Rp) y la del secundario |
| SCT013-**000** + J4 | jack 3,5 mm hembra stereo sin contacto de conmutación | **CONFIRMAR la pieza**: el modelo usa 100 A : 50 mA (2000:1) con burden externo, que es la SCT-013-**000**. La SCT-013-**100** es la de salida 1 V con burden interno y no sirve con Rbi. Verificar con multímetro cuál pin es punta y cuál manga |
| F1 | 100 mA T, 250 VAC + portafusible | |
| Rp1 / Rp2 | 62 kΩ 2 W / 56 kΩ 1 W, 1 % | JP1 puenteando Rp2 = Colombia (62 k); abierto = Chile (118 k) |
| Rbv | 470 Ω 1 % | |
| Rbi | 30 Ω 1 % | |
| Rfv / Rfi | 3,3 kΩ / 3,74 kΩ 1 % | Rfi con E24: 3,6 kΩ + 150 Ω |
| Cfv, Cfi | 10 nF película PP o C0G, 2 % | emparejar con LCR si se puede |
| Rsv, Rsi | 1 kΩ | |
| D1v, D2v, D1i, D2i | 1N4148 | |
| R_A, R_B2 | 10 kΩ 0,1 % (1 % sirve) | |
| C_V1, C_V2 | 10 µF, 100 nF | |
| R_B, R_BI | 2,2 kΩ | solo banco |
| SW1, JP1, JP4, SW3 | conmutador SPDT / jumpers | SW1 debe ser de apertura antes de cierre |

## 5. Resultados (Colombia 60 Hz/120 V y Chile 50 Hz/220 V)

Detalle completo en **`sim/RESULTADOS_LTspice.md`**.

- **LTspice vs ngspice vs Python:** coinciden a 0,0003 % en módulo y 0,0000° en fase (50/60 Hz); el transitorio, a ≤0,011 mV (0,014 LSB).
- **Picos en el pin ADC:** Colombia V 0,364–2,936 V, I 0,908–2,392 V. Con V al 120 % y I al 200 %: V 3,194 V, I 3,135 V, con 3,30 V de límite → **margen 106 mV**.
- **Filtro:** RC igual en ambos canales, fc ≈ 4,22 kHz. Atenuación respecto a 60 Hz: −6,2 dB a 7,5 kHz. Con el CIC3 en cascada, el peor rechazo de toda la banda es **−17,3 dB a 7,5 kHz** (el Nyquist de la salida de 15 kS/s).
- **Clamps:** en operación normal, incluida la sobrecarga, los 1N4148 pasan 7,8 nA (fuga). A 400 % limitan el pin a −0,58 / +3,88 V con 0,6 mA.
- **Muestreo del ADC:** τ = 10 ns, 12 bits piden 90 ns, hay 4,10 µs → **margen 46×**. Error simulado 0,003 LSB.
- **Transformadores (corregido):** ya no son ideales. El ZMPT101B adelanta 0,69° a 60 Hz y el SCT-013 0,83°, así que **la fase V−I no es 0 sino −0,144°** (60 Hz) y −0,173° (50 Hz). La calibración de 1 punto la quita en f0, pero no fuera de f0.
- **Cadena completa (200 combinaciones, percentil 95):** sin calibrar, TVE ≈ 2,1–2,7 %. Con calibración de 1 punto: TVE ≤ 0,013 % en nominal; **0,15–0,27 % a f0 ± 5 Hz** (antes se creía 0,015 %, con los transformadores ideales); con corriente al 10 %, TVE_I ≈ 0,13 %; fase V−I ≤ 0,068 °; frecuencia ≤ 6,3 mHz. Todo bajo el 1 % de clase M.
- **Propuesto (no aplicado):** compensar también el polo del transformador en el modelo nominal del firmware baja el TVE a f0 ± 5 Hz a 0,04–0,075 % (3,6×). Es software puro: `python sim/simulate_chain.py --ct-nom`.

## 6. Qué NO cubre esta simulación

- El desfase de los sensores ya **no** es un supuesto constante: sale de un modelo con magnetizante, con `Lm` derivada del límite de la hoja del ZMPT101B (≤20′ con 100 Ω). Pero `Rw` (150 Ω / 20 Ω) y el dato de fase del SCT-013 (1°) siguen siendo supuestos: ver los puntos CONFIRMAR de `sim/RESULTADOS_LTspice.md`.
- No se modela la saturación del núcleo (no hay curva B-H). A 120 % de tensión y 200 % de corriente se está dentro de lo nominal de las dos piezas.
- Ruido del ADC fijado en 1,5 LSB rms. **Medido** en la placa (`STM32/uPMU/docs/RESULTADOS.md`): 0,62–0,66 LSB propios del ADC y hasta 1,40 LSB en entrada externa con cable, así que el supuesto es conservador. No hay INL ni ruido de layout.
- El ruido de VDDA **no** se cancela por ser ratiométrica la medida: el offset sí (VCM sale de VDDA), pero la señal viene de la red y su código escala con 1/VDDA. Ver §7 de `sim/RESULTADOS_LTspice.md`.
- Sin armónicos ni interferencia fuera de banda: la ventana Hann de 4 ciclos ya se había señalado como débil frente a esa prueba de la norma.
- El error de tiempo del PPS (GPS) se asume corregido; se evalúa aparte.
- Las asignaciones de pines y el plan de temporización de la hoja 2 hay que confirmarlos contra UM1956 y RM0316 antes de cablear.
