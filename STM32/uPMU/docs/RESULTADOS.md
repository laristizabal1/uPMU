# Resultados uPMU (NUCLEO-F303K8 + GPS)

Solo cifras con log en `data/`. Lo no confirmado se marca CONFIRMAR.

## Notas de entorno

- 2026-10-10, T1.1: `pio run -t upload` (OpenOCD) fallaba con `LIBUSB_ERROR_NOT_FOUND` por falta de driver en la
  interfaz "ST-Link Debug" (MI_00). Se instaló WinUSB con Zadig (winget `akeo.ie.Zadig`) y el upload quedó funcionando
  (`Verified OK`). COM6 = puerto serie virtual. Respaldo: copiar el `.bin` a la unidad `NODE_F303K8`.
- Banderas `-mfpu=fpv4-sp-d16 -mfloat-abi=hard` en `build_flags` rompen el enlazado (CONFIRMAR para Fase 4).

## T1.2 Reloj del sistema (2026-10-10)

- UM1956 Rev 3, sec. 6.8 y Tabla 5: placas STM32Fxxx salen sin cristal (X1) y con **HSI** por defecto
  (SB4 OFF, SB17 OFF, SB6 ON, SB8 ON, SB5/SB7 OFF). MCO 8 MHz del ST-LINK a OSC_IN (PF0) = SB4 ON, SB6 OFF.
- Cabecera del HAL (RM0316): en F303x8 `PLLSRC` es 1 bit: HSI/2 o HSE/PREDIV. Con HSI el PLL llega a 4 MHz x 16 = 64 MHz.
- Medicion en la placa: HSE en bypass no arranca (`hal_status=3` HAL_TIMEOUT, `HSERDY=0`, `HSEBYP=1`).
  Log: `data/t1_2_hse_probe_20261010.csv`. Conclusion: la placa esta en configuracion HSI (SB4 abierto).
- Decision (Luis, 2026-10-10): **opcion B**, sin soldar: HSI/2 x PLL15 = **60 MHz** nominales, PCLK1 = 30 MHz,
  flash 2 WS. Con 60 MHz, ARR = 999 da 60 kS/s nominales (T3.1). Pendiente CONFIRMAR frecuencia real con el PPS (T2.2).
- Medicion (2026-10-10, `data/t1_2_clk_20261010.csv`, 65 s, referencia = reloj de la PC, **no** el PPS):
  el HAL reporta sysclk = 60 000 000 Hz; el periodo real de "1 s" del Nucleo es 1,001029 s, es decir el reloj va
  ~1029 ppm lento (equivale a ~59,938 MHz). Residuo 0,5 ms rms. Cifra provisional hasta T2.2 con el PPS.
- Estado: T1.2 cumplida (frecuencia del sistema confirmada y documentada).

## T1.3 NMEA por UART (2026-10-10)

- Cableado: el GPS tenia TXD/RXD cruzados respecto a la §2 (se vio en consola ~880 transiciones/s en PA9 y
  ninguna en PA10); corregido por Luis. USART1 9600 8N1, IRQ + buffer circular de 512 B, reenvio a USART2.
- Log `data/t1_3_gps_nmea_20261010.csv` (30 s, GPS ya encendido, sin fix, antena en interior):
  153 sentencias, **153 con checksum correcto, 0 malas**, 0 desbordes del buffer, 0 errores ORE/FE/NE.
  Tipos: GLL, RMC, VTG, GGA, GSA, GSV (1 por segundo cada una); `fix=0`, 0 satelites.
- Sin lineas `$..TXT` en esa captura (el GPS ya estaba encendido); ver el log de arranque mas abajo.

## T1.3 Modelo del GPS (2026-10-10)

- Placa azul, rotulada **NEO-7M** (dicho por Luis). Log de arranque tras reconectar 3V3:
  `data/t1_3_gps_boot_20261010.csv` (120 s, 618 sentencias, 618 con checksum correcto).
- Lineas `$GPTXT` de arranque (identifican el chip):
  - `u-blox ag - www.u-blox.com`
  - `HW  UBX-G70xx   00070000`
  - `ROM CORE 1.00 (59842) Jun 27 2012 17:43:52`
  - `PROTVER 14.00`
  - `ANTSUPERV=AC SD PDoS SR` y luego `ANTSTATUS=DONTKNOW` -> `INIT` -> `OK`
- Conclusion: chip **u-blox 7 (UBX-G70xx)**, ROM 1.00, protocolo 14.00; coincide con un NEO-7M. Las lineas TXT
  no distinguen entre variantes u-blox 7 (NEO-7M/7N, etc.); la variante exacta sigue siendo la del rotulado.
- Estado: T1.3 cumplida (NMEA con checksum correcto cada segundo, TXT guardadas).

## T1.4 Parser NMEA (2026-10-10)

- `src/nmea.c` + `include/nmea.h`: parser byte a byte de GGA/RMC (cualquier talker), checksum XOR, sin HAL.
  Descarta y cuenta sentencias con checksum malo, sin `*`, demasiado largas, con basura o cortadas por otro `$`.
- Salida por el puerto virtual: `STATE,<ddmmyy>T<hhmmss.ss>,<fix>,<sats>` una vez por segundo (al llegar la GGA;
  fecha desconocida = `------`, sin hora = campo vacio) y `#NMEA,ok=<n>,bad=<n>` cada 10 s.
- Prueba en la PC (`tools/test_nmea.py`, compila el mismo `nmea.c`): 771 sentencias reales de
  `data/t1_3_*.csv` con el mismo conteo que la referencia en Python (0 malas) y casos sinteticos
  (fix 1 y 4, talker GN, checksum malo, linea larga, `$` a mitad de linea, `\n` solo).
- Prueba en la placa: `data/t1_4_state_20261010.csv` (25 s): 1 STATE por segundo, `#NMEA,ok=98,bad=0`.
  Sin fix y antena en interior: `STATE,,0,0`.
- CONFIRMAR en T1.5: la rama con fix > 0 solo se ha probado con sentencias sinteticas; falta verla con
  sentencias reales del GPS.

## T1.5 Primer fix (2026-10-10) - NO CUMPLIDA

- Captura `data/t1_5_fix_20261010.csv`: 15 min (23:25-23:40) con la antena afuera, desde arranque en caliente
  del Nucleo: 900 STATE, **ninguno con fix > 0**, satelites usados = 0 en todas. 6167 sentencias, 0 con checksum malo.
- Diagnostico `data/t1_5_gsv_diag_20261010.csv` (30 s, build con -DNMEA_ECHO): el modulo solo reporta GSV de
  **1 satelite a la vez** (PRN 14 y PRN 10, SNR 28 dB-Hz; en una captura anterior PRN 29, SNR 23 dB-Hz).
  Hace falta ver >= 4 para fijar; 28 dB-Hz es una senal debil para cielo abierto (CONFIRMAR con una referencia).
- Causa no determinada: vista de cielo obstruida y/o antena poco adecuada. Pendiente: otra ubicacion y revisar la antena.
- Segundo intento (Luis cambio la antena de sitio), `data/t1_5_fix_b_20261010.csv`: 7 min (23:45-23:52,
  limite fijado por Luis), 426 STATE, **ninguno con fix > 0**, 0 satelites usados. El modulo entrega
  fecha y hora UTC (411 de 428 STATE), pero sin fix esa hora puede venir de su RTC/estimacion, no de los
  satelites: no prueba recepcion (CONFIRMAR).
- Estado: **T1.5 bloqueada por el entorno** (Luis: no hay mejor sitio disponible por ahora). Se retoma cuando haya
  vista de cielo abierta. Afecta a T2.1 a T2.4 y T5.1/T5.2 (necesitan PPS con fix).

## T1.5 Diagnostico RF del GPS por UBX (2026-10-10)

- Firmware con `-DUBX_DIAG` + `tools/ubx_diag.py`; formatos verificados en u-blox 7 Receiver Description V14
  (GPS.G7-SW-12001-B): MON-HW 60 B, NAV-SVINFO 8+12*numCh, NAV-STATUS 16 B. Logs: `data/t1_5_ubx_diag_20261010.bin`
  (crudo) y `.txt` (decodificado), 25 s, 8 consultas de cada tipo, todas con checksum UBX valido.
- Comunicacion en **ambos sentidos** comprobada (el modulo responde a las consultas por PA9 -> RXD).
- MON-VER: sw `1.00 (59842)`, hw `00070000`, ext `PROTVER 14.00`, `GPS;SBAS;GLO;QZSS`.
- MON-HW: antena `OK`, alimentacion de antena `ON`, `agcCnt` = 4453/8191 (constante), `noisePerMS` = 105-112,
  `jamInd` = 5-7/255 (sin interferencia CW apreciable), `jammingState` = desconocido/desactivado.
- NAV-SVINFO: **0 satelites con senal** en las 8 consultas; todos los canales en `buscando` barriendo SV1-SV32.
- NAV-STATUS: `sin fix`, `gpsFixOk=0`, 838-859 s desde el arranque del modulo.
- Lectura: el modulo, el UART y la antena (segun su supervisor) estan operativos y sin interferencia fuerte,
  pero el receptor no adquiere ningun satelite: la senal que llega a la antena es insuficiente (vista de cielo
  y/o antena). Un defecto del LNA o del conector no se puede descartar desde el software. CONFIRMAR con otro
  sitio o antena. No hay referencia de valores "normales" de agcCnt/noisePerMS en la especificacion.

## T1.5 Modulo GPS conectado directo al PC por USB (2026-10-11)

- Luis conecto el modulo por su USB propio: aparece como COM7, VID 1546 (u-blox AG), sin Nucleo en el bus.
  `tools/ubx_diag.py 14 COM7 poll` -> `data/t1_5_ubx_diag_20261011.bin` / `.txt` (14 s, 5 consultas de cada tipo,
  todas validas).
- Mismo chip: MON-VER `1.00 (59842)`, hw `00070000`, `PROTVER 14.00`.
- MON-HW: antena `OK`/`ON`, `agcCnt` = 4599 (antes 4453 con el Nucleo), `noisePerMS` = 110 (antes 105-112),
  `jamInd` = 4-18/255. Sin fix; 45-57 s desde el arranque del modulo.
- NAV-SVINFO: en 1 de 5 consultas un SV (27) a 28 dB-Hz "adquirida"; el resto sin senal. Mismo patron que
  con el Nucleo: **la alimentacion/ruido del Nucleo no explica la falta de fix**.
- Monitor en vivo `tools/ubx_watch.py` (COM9, el modulo cambio de numero al reenchufarlo), 420 s,
  `data/t1_5_watch_20261011.csv`: **sin fix en ningun momento**, a lo sumo **1 satelite con senal a la vez**
  (24-28 dB-Hz), en episodios de ~2 s cada 15-30 s, sin llegar nunca a usarse en la solucion.

## T3.1/T3.2 Reloj de muestreo y ADC dual (2026-10-11)

- TIM2 (SYSCLK 60 MHz, APB1 x2) ARR = 999 -> 60 kHz, TRGO por update -> ADC1 (PA0, IN1) + ADC2 (PA4, IN1) dual
  simultaneo (ADC_DUALMODE_REGSIMULT, MDMA 12 bit), reloj ADC AHB/4 = 15 MHz, muestreo 61,5 ciclos, un DMA
  circular de 512 palabras (2 mitades de 256 muestras, 4,27 ms), palabra = ADC2<<16 | ADC1.
- Log `data/t3_2_adc_20261011.csv`, 605 lineas consecutivas (00:39:13-00:49:18, 604 s entre la primera y la ultima):
  muestras 2 639 872 -> 38 879 744 = 36 239 872 en 604 s = **59 999,79 muestras/s** (esperado 60 000; la diferencia
  de 128 es menor que la granularidad de 256). Delta por segundo 59 904/60 160. **ovr ADC = 0, mitades sin procesar = 0,
  perdidas de la cola de salida = 0** durante toda la corrida. TIM2 y SysTick salen del mismo reloj, asi que
  el conteo en segundos de SysTick no detecta el error de ~1029 ppm del HSI (eso es T2.2 con el PPS).
- Entradas sin conectar (flotantes): A ~ 99-102 LSB (min 42-73, max 112-166), B ~ 87-89 LSB; solo informativo.
- Ajuste de herramientas: OpenOCD supone 16 KB de SRAM; con binarios > ~8 KB escribia fuera de los 12 KB reales
  (`Failed to write memory at 0x20003008`). `platformio.ini`: `set WORKAREASIZE 0x2000`.

## T3.1 Ubicar el PPS en el flujo de muestras (2026-10-11)

Opcion A (acordada): muestras = vueltas*512 + (512 - NDTR) del DMA; fase = TIM2->CCR2 (ticks de 60 MHz).
Pruebas con capturas por software (`TIM2->EGR = CC2G`), sin PPS real ni cable:
- `data/t3_1_pps_sw_20261011.csv` (25 pulsos, 1 Hz): el conteo avanza ~60 000 por pulso (59 982..60 020; el jitter
  es del pulso de prueba generado en el bucle principal), sin saltos de 256/512.
- `data/t3_1_pps_stress_20261011.csv` (180 s, 1000 capturas/s desde SysTick): 179 999 capturas, 0 con delta
  fuera de 59-61 muestras. La rama de carrera (TC pendiente) se ejecuto **0 veces**: SysTick esta en fase fija
  con el muestreo, asi que esta prueba no la ejercita.
- Calibracion `data/t3_1_pps_cal_20261011.csv` (75 s, TIM3 cuenta por hardware los disparos de TIM2 como
  referencia; capturas cada 59 999 ticks que barren todas las fases, ~3700 por bucket de 50 ticks):
  la diferencia (disparos - muestras del DMA) vale 0 para fase < ~265 y -1 para fase >= 300; el bucket 250-299
  se reparte 1598/2169. Es decir, el DMA entrega la muestra ~**271 ticks (4,5 us)** despues del disparo
  (conversion + DMA + latencia de la ISR). El desfase absoluto de -1 es el offset de arranque de TIM3.
  Consecuencia: con la opcion A el indice exacto del disparo es `N + (fase < ~271 ? 1 : 0)`, con ~+-30 ticks de
  incertidumbre en el umbral (~6 % de los PPS caen cerca) y error de 1 muestra (16,7 us = 0,36 deg a 60 Hz) si se
  clasifican mal.
- CONFIRMAR: PA1 = TIM2_CH2 en AF1 (solo probado la captura por software, no el pin); falta cablear D13 -> A1.

## T3.1 Comparacion A vs B y decision (2026-10-11)

Verdad independiente: TIM6 dispara capturas por software cada 59 999 ticks exactos, asi que
`T = k*1000 + fase` debe avanzar 59 999 (+-latencia de la ISR de TIM6); 1 muestra mal = +-1000.
Todas con ~190 000 pares (barrido de fases) sobre `data/t3_1_pps_cmp_20261011.csv`:

| Metodo | Pares mal (>500 ticks) | Nota |
|---|---|---|
| A: DMA + umbral de fase 271 (lectura inmediata) | 852 de 190 002 (0,45 %) | todos en +-40 ticks del umbral (5,3 % de los pares cercanos) |
| B: TIM3 por hardware, lectura inmediata | 824 de 190 002 (0,43 %) | errores solo con TIM2->CNT de 1 a 11 en la lectura: TIM3 va ~11 ticks por detras del TRGO (25-48 % de error en 1-7, 10 % en 9, 0,6 % en 11, 0 desde 13) |
| **A y B, esperando a la zona segura [340, 980] del periodo** | **0 de 190 002, ambos** | k == n_dma en todos los pulsos; rama de TC pendiente ejercitada 164 veces sin error; desviacion maxima 167 ticks (jitter de la ISR de TIM6, no error de muestra) |

- Decision: **B (k, contador de disparos por hardware) es el indice principal** por ser independiente de la
  latencia del DMA; **A (n_dma) se conserva como control de integridad** (k != n_dma = muestras perdidas por el DMA).
  Salida: `PPS,<n>,<fase>,<k>,<n_dma>`.
- Costo: la ISR del PPS (1 Hz) espera hasta ~1340 ticks (22 us) a la zona segura, antes de leer. Sin efecto en
  el DMA (buffer de 4,27 ms) ni en el UART (1 byte por ms).
- Con fase y k exactos, el error de sello es el de la fase (1 tick = 16,7 ns) y el jitter del PPS del GPS;
  ya no hay termino de 1 muestra (16,7 us = 0,63 % TVE a 60 Hz) que filtrar.
- Constante a compensar en T5.1: entre el disparo y la muestra entregada hay ~271 ticks (4,5 us), mas el
  retardo del CIC.
- Pendiente (necesita cable D13 -> A1 o PPS real): verificar PA1 = TIM2_CH2 AF1 y la linea `PPS,...` por el pin.

## T3.1 verificacion del pin PPS (2026-10-11)

- Cable D13 (PB3) -> A1 (PA1), build `-DPPS_SELFTEST` (pulso de 1 Hz, 100 ms): `data/t3_3_adc_known_20261011.csv`,
  40 pulsos, **todos capturados por PA1**, k == n_dma en 40/40. Confirma **PA1 = TIM2_CH2 en AF1** (CONFIRMAR
  resuelto empiricamente). El jitter entre pulsos (59 979-60 021 muestras) es del pulso de prueba por software.

## T3.3 Entradas conocidas (2026-10-11)

- PA0 -> GND, PA4 -> 3V3 con cables, 40 s en `data/t3_3_adc_known_20261011.csv`:
  A (PA0) media **0,35 LSB** (picos aislados hasta 90), B (PA4) media **4088,7 LSB**, min 4077, max 4095.
  Sin overruns ni perdidas. Cumple "~0 y ~4095, estables" con la nota: B queda ~6 LSB (0,15 %) bajo el fondo de
  escala; no atribuido (CONFIRMAR con el error total sin ajustar del datasheet; la calibracion del ADC solo
  corrige offset). Los picos en A (11-90 LSB, esporadicos) persisten sin el pulso de PB3: origen sin determinar.

## T3.4 Ruido del ADC, GPS encendido (2026-10-11)

Desviacion estandar por ventana de 1 s (60 000 muestras), con el GPS alimentado y transmitiendo (`#NMEA` creciente):

| Entrada | Log | media (LSB) | sigma (LSB rms) |
|---|---|---|---|
| VREFINT en ADC1 | `data/t3_4_noise_vref_adc1_20261011.csv` (17 s) | 1511,0 | **0,66** (0,66-0,67) |
| VREFINT en ADC2 | `data/t3_4_noise_vref_adc2_20261011.csv` (17 s) | 1510,3 | **0,62** (0,61-0,62) |
| PA0 -> GND | `data/t3_4_noise_gnd_vcc_20261011.csv` (25 s) | 0,2 | 0,82 (recortada en 0) |
| PA4 -> 3V3 | idem | 4089,1 | 1,40 (1,33-1,46) |

- La simulacion supuso 1,5 LSB rms: **no se supera ni el umbral de aviso de ~2**.
- VREFINT: segun RM0316 (nota del HAL) solo un ADC puede estar conectado a VREFINT a la vez, por eso se midio por separado.
- PA4 -> 3V3 es mayor (1,40 frente a ~0,65 de VREFINT); probablemente es ruido de la linea de 3V3 del Nucleo
  que llega por el cable y no por VDDA (hipotesis, CONFIRMAR). El ruido propio del ADC es ~0,6-0,7 LSB.
- Pendiente T3.5: repetir con el VCC del GPS desconectado.

## T3.5 Ruido con el GPS apagado (2026-10-11)

VCC (3V3) del GPS desconectado por Luis; sin sentencias NMEA en los logs (confirma GPS apagado).
Logs `data/t3_5_nogps_{vref_adc1,vref_adc2,gnd_vcc}_20261011.csv`, mismas duraciones y builds que en T3.4:

| Entrada | GPS | media (LSB) | sigma (LSB rms) | min / max | segundos con pico > 10 LSB |
|---|---|---|---|---|---|
| VREFINT ADC1 | ON / OFF | 1511,0 / 1508,7 | 0,66 / **0,64** | 1506-1515 / 1506-1513 | 0/17 / 0/17 |
| VREFINT ADC2 | ON / OFF | 1510,3 / 1509,3 | 0,62 / **0,64** | 1508-1515 / 1507-1514 | 0/17 / 0/17 |
| PA0 -> GND | ON / OFF | 0,2 / 0,0 | 0,82 / **0,32** | 0-68 / 0-38 | 22/25 / 18/24 |
| PA4 -> 3V3 | ON / OFF | 4089,1 / 4089,1 | 1,40 / **1,07** | 4076-4095 / 4083-4095 | 2/25 / 0/24 |

- El ruido propio del ADC (VREFINT) **no cambia** con el GPS (0,62-0,66 frente a 0,64 LSB rms).
- En las entradas externas por cable el ruido **si baja** sin GPS: PA0 -> GND de 0,82 a 0,32 LSB rms y
  PA4 -> 3V3 de 1,40 a 1,07 (-24 %). Es un aporte del GPS por alimentacion/tierra comun o acoplamiento al cableado.
  No separado entre ambos (CONFIRMAR).
- Los picos esporadicos en PA0 -> GND **persisten sin GPS** (18 de 24 s, max 38 frente a 68-90 con GPS): el GPS
  los agranda pero no los origina; origen sin determinar.
- La media de VREFINT baja 1-2 LSB sin GPS (VDDA algo mayor): compatible con menor caida de la linea de 3V3,
  hipotesis sin verificar.
- Con GPS encendido todo queda < 1,5 LSB rms (peor caso 1,40), por debajo del umbral de aviso de 2.

## T3.5 Con 10 uF + 100 nF junto al GPS (2026-10-11)

Luis agrego 10 uF + 100 nF entre VCC y GND del modulo; GPS encendido y transmitiendo (`#NMEA` creciente,
`bad=0`). Logs `data/t3_5_caps_{vref_adc1,vref_adc2,gnd_vcc}_20261011.csv`, mismas builds y duraciones.

| Entrada | GPS ON sin caps | **GPS ON con caps** | GPS OFF |
|---|---|---|---|
| VREFINT ADC1 (sigma, LSB rms) | 0,66 | **0,62** | 0,64 |
| VREFINT ADC2 | 0,62 | **0,62** | 0,64 |
| PA0 -> GND | 0,82 | **0,30** | 0,32 |
| PA4 -> 3V3 | 1,40 | **1,14** | 1,07 |
| PA0 -> GND, maximo (LSB) | 68 | 35 | 38 |

- Con los condensadores el ruido con GPS encendido iguala al del GPS apagado (PA0: 0,30 frente a 0,32) o queda a
  0,07 LSB (PA4: 1,14 frente a 1,07). **El aporte del GPS llegaba por la alimentacion/tierra.**
- Los picos esporadicos en PA0 siguen (35 LSB) igual que sin GPS: no dependen del GPS; origen sin determinar.

## T4.1 Vectores de prueba y transmision por serie (2026-10-11)

- `tools/gen_vectors.py` (usa `ref/` solo en lectura) genera 14 vectores en `data/vectors/`: 2 redes (Colombia 60 Hz /
  Chile 50 Hz) x 7 escenarios de `ref/simulate_chain.py` (nominal, V 80 %/I 10 %, V 120 %/I 200 %, f0 +-2 Hz,
  f0 +-5 Hz), ruido de 1,5 LSB rms, un .bin (codigos del ADC a 60 kS/s, uint16 LE intercalados V/I; 4018 muestras
  a 60 Hz, 4818 a 50 Hz) y un .json (estadistica y salida esperada de la referencia). Para cada uno se verifica que
  el CIC de `ref` sobre mis codigos reproduce exactamente `acquire()` con la misma semilla.
- Salida esperada de la referencia (TVE de la simulacion, por vector): V 0,001-0,013 %, I 0,003-0,121 %
  (la peor es "V 80 %, I 10 %" de Chile, coherente con `ref/results_chain.txt`).
- Protocolo PC -> Nucleo por el VCP (USART2 RX, PA15 AF7): `55 56 | n_in u16 | f0 u8 | flags u8 | n_in*{V u16,I u16} |
  CRC32`. `src/vecrx.c` (sin HAL) recibe en flujo (no cabe en RAM) y devuelve
  `VEC,<estado>,<n_in>,<f0>,<crc>,<sumV>,<sumI>,<minV>,<maxV>,<minI>,<maxI>,<rx_overflow>,<rx_err>`.
- Verificado: `tools/test_vecrx.py` (mismo C en la PC): 14/14 vectores con estadistica y CRC identicos, CRC malo,
  cabeceras invalidas, resincronizacion y timeout. En el Nucleo: `tools/send_vector.py` envia cada vector
  (16 082 / 19 282 bytes en 1,4-1,7 s) y el resultado coincide; con un byte corrompido responde `CRC`.
  Sin desbordes (`rx_overflow = 0`) con el ADC y el GPS corriendo a la vez. RAM 4960 B de 12 288.

## T4.2 CIC de orden 3, R = 4, aritmetica entera (2026-10-11)

- `src/cic.c` + `include/cic.h`: integradores (60 kS/s) y peines (15 kS/s) con aritmetica modular de 32 bits,
  exacta porque la salida cabe en 18 bits (4095 * 64 = 262 080). Salida entera `S = 64 * codigo filtrado`, sin
  redondeo (equivale a `np.convolve(c, [1 3 6 10 12 12 10 6 3 1])[9::4]`; `ref` usa esas mismas 10 taps / 64).
  El transitorio (indices < 9) se descarta, como en `ref`. Retardo de grupo 4,5 muestras de 60 kS/s = 75 us.
- Verificacion (mas fuerte que comparar muestras sueltas): CRC32 de las 2*n_out salidas int32 (V e I intercalados),
  suma de cada canal y primer/ultimo valor, firmware contra Python, para los 14 vectores:
  - mismo C en la PC (`tools/test_vecrx.py`): 14/14 identicos;
  - en el Nucleo (`tools/send_vector.py`, linea `CIC,<n_out>,<crc>,<sumV>,<sumI>,...`): **14/14 identicos**
    (1000 salidas x 2 a 60 Hz, 1200 x 2 a 50 Hz).
  - `gen_vectors.py` ademas comprueba que `S/64 * LSB` es exactamente la salida de `S.acquire()` (diferencia 0).
- Diferencia respecto a Python: **0 LSB** (identico bit a bit), mejor que el criterio de <= 1 LSB.
- Para T4.3: la ventana (1000 o 1200 muestras x 2 canales) se guardara como `uint16 = S >> 2` (65 520 max,
  resolucion 0,25 codigos, ruido de cuantizacion despreciable frente a los ~0,56 LSB del CIC): 4,0 / 4,8 KB.
  Guardar S en int32 (8-9,6 KB) no cabe junto al resto de la RAM (4,96 KB usados de 12).

## T4.3 IpDFT + ajuste sinusoidal (2026-10-11)

- `src/estimator.c` + `include/estimator.h`: IpDFT con ventana Hann (formula de Grandke), minimos cuadrados con
  peso w^2 y 4 iteraciones de Gauss-Newton sobre f, como `ipdft_ls()` de `ref` (que es float64). float32 con FPU.
  Entrada: S exacto del CIC guardado como `hi = S >> 2` (uint16) + `lo` (2 bits, 4 por byte), 2,25 B/muestra.
- Primer intento con `S >> 2` solo: el error de cuantizacion hacia 0,00106 deg en el ajuste de I (escenario I 10 %),
  apenas sobre el objetivo; float32 y double daban lo mismo, es decir era almacenamiento y no numerica. Con los 2 bits
  bajos recuperados el algoritmo en double reproduce a `ref` con error 0.
- Verificacion en la PC (`tools/test_est.py`, mismo C): peor caso de los 14 vectores, float32:
  **0,0038 mHz, 0,00014 % (V), 0,00014 % (I), 0,00005 deg (V), 0,00005 deg (I)**.
- Verificacion en el Nucleo (`tools/send_vector.py`, linea `EST,...`), 14/14 PASS, peor caso: **0,0046 mHz,
  0,00015 % en modulo, 0,00005 deg en angulo** (objetivo: < 1 mHz, < 0,001 %, < 0,001 deg: cumplido con un
  orden de magnitud de margen). Referencia: TVE de la simulacion de `ref` 0,001-0,121 %.
- FPU de hardware: `build_flags` con `-mfloat-abi=hard` no llegaba al enlazado (pendiente desde T1.1); se resolvio
  con `fpu.py` (pre-script de PlatformIO que agrega las banderas a CCFLAGS y LINKFLAGS).
- RAM: 7360 B de 12 288 (SRAM) + 3000 B en CCM-RAM (V y los dos `lo`); flash 26,2 KB de 64 KB.
- **Tiempo (primera medicion, base de T4.4):** 21,7 M ciclos a 60 Hz (362 ms a 60 MHz) y 26,0 M ciclos a 50 Hz
  (433 ms) para los dos canales. **No cumple para tiempo real** (la ventana dura 66 ms / 80 ms): ~60 000 llamadas
  a sinf/cosf a ~360 ciclos cada una (newlib usa doble precision por dentro).

## T4.4 Tiempo y memoria (2026-10-11)

Objetivo acordado con Luis: **30 fps a 60 Hz y 25 fps a 50 Hz** (cubren los +-5 Hz de clase M) => presupuesto por
ventana de 2,0 M ciclos (33 ms) a 60 Hz y 2,4 M ciclos (40 ms) a 50 Hz, a 60 MHz.

Ciclos con el contador DWT (dos canales, V e I, sobre la ventana de 4 ciclos), medidos en el Nucleo con el ADC
a 60 kS/s, el GPS y las interrupciones corriendo (14 vectores, `tools/send_vector.py`):

| Version | 60 Hz (1000 muestras) | 50 Hz (1200 muestras) |
|---|---|---|
| T4.3 inicial (sinf/cosf por muestra, 4 iteraciones) | 21,7 M | 26,0 M |
| Rotaciones complejas + reanclaje, tablas de la ventana Hann cacheadas | 3,84 M | 4,60 M |
| + acumuladores en registros, DFT desenrollada, 5 bines, 2 iteraciones | **1,13-1,16 M** | **1,36-1,39 M** |
| Presupuesto (30 / 25 fps) | 2,0 M | 2,4 M |
| **Uso del presupuesto** | **57 %** (19 ms) | **58 %** (23 ms) |

- Perfil final a 60 Hz (suma de los dos canales): DFT 0,26 M, ajustes 0,44 M, barridos de residuo 0,32 M,
  semillas trigonometricas 0,08 M, tablas (una sola vez por N) 0,03 M. `-O2` solo no cambio nada (3,92 M); lo que
  pesaba era el acceso por memoria de los acumuladores y los bucles de la DFT.
- Margen: **no alcanza 60 / 50 fps** (1,0 / 1,2 M ciclos); habria que optimizar mas los barridos (~75 ciclos/muestra).
- Memoria: RAM estatica 7796 B de 12 288 (incluye la ventana: `hi_i` 2,4 KB), mas 3000 B en CCM-RAM (`hi_v` y los
  dos `lo`); margen minimo medido entre el fin de .bss y la pila/heap: **3132 B**. Flash 28,5 KB de 64 KB (la libm
  pesa ~8 KB).
- Exactitud tras optimizar (14 vectores en el Nucleo, referencia float64): peor frecuencia **0,0054 mHz**, modulo
  **0,00016 %**, angulo **0,00005 deg**. Cambios de algoritmo respecto a `ref`, con efecto medido < 0,01 mHz:
  2 iteraciones de Gauss-Newton en vez de 4 (en double el resultado es identico) y candidatos del pico en k0 +-1
  en vez de k0 +-2 (cubre f0 +- 22 Hz).
- Uso de CPU: con la ventana a 30 fps el estimador consume ~57 % del procesador; queda ~43 % para el CIC en
  tiempo real, el ADC, el GPS y la salida (T5.x).

## T4.5 Verificacion completa: TVE del firmware frente a la simulacion (2026-10-11)

`tools/verify_all.py` corre los 14 vectores por el Nucleo (`send_vector.py`), toma la linea `EST`, aplica la cadena
fisica de `ref` (H nominal, ganancia del CIC y `kappa` del JSON) y calcula el TVE contra el fasor verdadero. Log:
`data/t4_5_tve_20261011.csv`. Alcance igual al de `ref`: analogico + ADC (ruido 1,5 LSB) + CIC + estimador; fuera
quedan el error de tiempo del PPS y el desfase real de los sensores (se calibra, ver CLAUDE.md §8).

| Red | Escenario | f verdadera | f firmware | TVE_V sim / fw (%) | TVE_I sim / fw (%) |
|---|---|---|---|---|---|
| 50 Hz | f0 - 5 Hz | 45,0 | 44,9999 | 0,0030 / 0,0031 | 0,0122 / 0,0122 |
| 50 Hz | f0 - 2 Hz | 48,0 | 48,0002 | 0,0043 / 0,0043 | 0,0039 / 0,0039 |
| 50 Hz | nominal | 50,0 | 49,9997 | 0,0097 / 0,0097 | 0,0032 / 0,0032 |
| 50 Hz | f0 + 2 Hz | 52,0 | 51,9998 | 0,0011 / 0,0010 | 0,0036 / 0,0036 |
| 50 Hz | f0 + 5 Hz | 55,0 | 55,0004 | 0,0034 / 0,0034 | 0,0044 / 0,0045 |
| 50 Hz | V 80 %, I 10 % | 50,0 | 49,9974 | 0,0044 / 0,0044 | 0,1207 / 0,1208 |
| 50 Hz | V 120 %, I 200 % | 50,0 | 50,0001 | 0,0033 / 0,0034 | 0,0068 / 0,0067 |
| 60 Hz | f0 - 5 Hz | 55,0 | 55,0002 | 0,0069 / 0,0068 | 0,0116 / 0,0116 |
| 60 Hz | f0 - 2 Hz | 58,0 | 57,9996 | 0,0070 / 0,0070 | 0,0061 / 0,0060 |
| 60 Hz | nominal | 60,0 | 60,0001 | 0,0065 / 0,0064 | 0,0047 / 0,0046 |
| 60 Hz | f0 + 2 Hz | 62,0 | 62,0003 | 0,0058 / 0,0058 | 0,0076 / 0,0075 |
| 60 Hz | f0 + 5 Hz | 65,0 | 64,9994 | 0,0126 / 0,0126 | 0,0075 / 0,0075 |
| 60 Hz | V 80 %, I 10 % | 60,0 | 59,9986 | 0,0036 / 0,0036 | 0,0443 / 0,0443 |
| 60 Hz | V 120 %, I 200 % | 60,0 | 60,0001 | 0,0030 / 0,0030 | 0,0081 / 0,0081 |

- **Peor TVE del firmware: 0,0126 % (V) y 0,1208 % (I)**, contra el limite de la norma de 1 % y el objetivo interno
  de 0,2 %. La peor corriente es la de "V 80 %, I 10 %" en 50 Hz (corriente al 10 %: el ruido pesa mas).
- **|TVE firmware - TVE simulacion| <= 0,00014 % (V) y 0,00011 % (I)**: el firmware coincide con la simulacion.
- Error de frecuencia contra la verdadera: hasta 2,57 mHz (mismo valor que da la simulacion en ese vector;
  es ruido del ADC, no del firmware: el firmware difiere de `ref` en 0,005 mHz).
- La fila de 14 vectores es una sola realizacion de tolerancias y ruido por red; el p95 sobre 200 combinaciones
  esta en `ref/results_chain.txt` (V <= 0,011 %, I <= 0,126 %) y es coherente con estos valores.

## T5 cadena en vivo: ADC -> CIC -> ventana circular -> estimador -> trama (2026-10-11)

- Arquitectura (`src/main.c`, `src/pipeline.c`): la ISR del DMA (prio 0, minima) solo marca la mitad lista y pide
  una ISR de software (EXTI0, prio 3, la menor) que hace la estadistica y el CIC por muestra y llena la ventana
  circular; el bucle principal estima y emite. Asi la captura del PPS (prio 0) no espera al DSP (~300 us/mitad).
  Ventana circular de N + 450 salidas (holgura = 30 ms): mientras el estimador lee, llegan salidas nuevas sin pisarla.
- Verificacion en la PC (`tools/test_pipe.py`, mismo C): para 60 y 50 Hz, con senales de 60,0 / 61,3 / 50,0 / 47,2 Hz,
  la ventana circular da **exactamente** (bit a bit) lo mismo que la ventana lineal; reportes cada `period` salidas
  desde que se llena N; deteccion de ventana pisada.
- En el Nucleo, entradas sin senal (PA0 a GND, PA4 a 3V3), 25 s, `data/t5_live_20261011.csv`:
  **750 lineas `PMU` en 25 s = 30 por segundo**, `skipped = 0`, `invalid = 0`, `proc_ovr = 0`; estimador
  1,42 M ciclos por reporte con todas las interrupciones corriendo (71 % del presupuesto de 2 M de 30 fps).
  Los valores de f/V/I de esa prueba no tienen significado (entrada continua).
- Regresion: `tools/verify_all.py` sobre los 14 vectores con la arquitectura nueva da **el mismo resultado**
  (|dTVE| <= 0,00014 %).
- RAM: 8768 B de 12 288 (SRAM) + 3713 B en CCM-RAM; flash 31,1 KB. Ventana CCM para V y SRAM para I.
- Selector PB0 (T5.3) y senal conocida en vivo (build `-DDAC_TEST`): ver las secciones siguientes.

## T5 cadena en vivo con senal conocida (DAC del Nucleo, build -DDAC_TEST) (2026-10-11)

Autoprueba sin generador: el DAC1 saca una senoidal de **60,300 Hz** (NCO a 12 kHz desde TIM6, derivado del mismo
reloj que el muestreo: el cociente f_senal / f_muestreo es exacto aunque el HSI este desviado), amplitud 620
codigos (0,5 V pico) sobre 2048 en PA4 (= ADC2_IN1, canal I, sin cable); PA0 (canal V) recibe la misma senal
por un cable A3 -> A0. Logs: `data/t5_dac_test_20261011.csv` (30 s, V sin cable) y `data/t5_dac_loop_20261011.csv`
(40 s, 1169 reportes `PMU`, sin omitidos ni invalidos, 30 por segundo).

| Medida | Resultado | Esperado |
|---|---|---|
| Frecuencia, 1169 reportes | media **60,3000 Hz**, sigma 0,0014 Hz, max |err| 0,0050 Hz | 60,3000 |
| Angulo V - I (mismo nodo, ADC1 vs ADC2) | media **-0,0002 deg**, sigma 0,0038 deg, max 0,012 deg | 0 (muestreo simultaneo) |
| Modulo I: estimador vs rms en el tiempo (ADC) | 446,99 vs 447,03 codigos = **-0,009 %** | 0 |
| Modulo V: estimador vs rms en el tiempo (ADC) | 438,81 vs 438,85 codigos = **-0,009 %** | 0 |
| Estabilidad del modulo I en 30 s | sigma 0,0026 A sobre 24,01 A = 0,011 % | - |
| Ciclos por reporte con todo corriendo | 1,46 M (73 % de 2 M) | < 2 M |

- Confirma de extremo a extremo (ADC real a 60 kS/s -> DMA -> CIC -> ventana circular -> IpDFT/LS -> conversion
  fisica) que el estimador en vivo reproduce el rms del dominio del tiempo y la frecuencia exacta, y que los dos
  ADC muestrean en el mismo instante (desfase < 0,012 deg ~ 0,2 us).
- **Hallazgo:** con el mismo nodo en PA4 y PA0, el ADC1 (V) mide **1,83 % menos** que el ADC2 (I): sigma en el
  tiempo 438,85 contra 447,03 codigos; el estimador sigue a cada canal (-0,009 %), asi que la diferencia esta en
  la entrada. No es ganancia intrinseca de los ADC: sobre VREFINT dieron 1511,0 y 1510,3 (T3.4). Causa sin
  determinar (el cable/pin A0 o la carga del DAC); se corrige con `kappa` por canal en la calibracion de 1 punto
  (CLAUDE.md §8). CONFIRMAR con el front-end real.
- La salida 2 del DAC (PA5 = A4) cableada a A0 no entrego senal en el primer intento (PA0 = 153 +- 33 codigos,
  flotante); no se determino si era el cable. La prueba de 30 deg V - I queda pendiente de repetirla.

## T5.3 Selector 50/60 Hz (PB0) (2026-10-11)

PB0 (D3) con pull-up interno; a GND = 50 Hz, abierto = 60 Hz; se relee cada segundo y un cambio reinicia la cadena
(`#MODE,f0=`). Senal de prueba del DAC a 50,300 Hz (`-DDAC_TEST -DDAC_TEST_MHZ=50300u`, PA4 = A3 -> A0):

- **Modo 50 Hz** (D3 a GND, `data/t5_sel50_20261011.csv`, 40 s): ventana 1200 salidas, **25 reportes por segundo**,
  0 omitidos y 0 invalidos; f = **50,3000 Hz** (sigma 0,0009 Hz, max |err| 0,0030 Hz); V - I = -0,0001 deg
  (sigma 0,0035 deg); 1,80 M ciclos por reporte (75 % del presupuesto de 2,4 M).
- **Cambio en caliente** (`data/t5_selswitch2_20261011.csv`, cable D3 -> GND retirado durante la captura): aparece
  `#MODE,f0=60` y la tasa pasa a **30,0 reportes por segundo** sin reiniciar el Nucleo; con la senal de 50,3 Hz
  todavia presente el estimador da 50,3006 Hz sobre la ventana de 60 Hz (el IpDFT cubre f0 +- 22 Hz).
- **Hallazgo corregido:** con una holgura de la ventana circular de 450 salidas, en 50 Hz *todos* los reportes
  salian invalidos (`reports=0, invalid=984`): el estimador tarda 30 ms = 450 salidas del CIC, exactamente la
  holgura. `PIPE_SLACK` paso a 600 (40 ms); con eso la ventana de 50 Hz usa 1800 palabras por canal y entra justa
  en la CCM-RAM (4050 B de 4096).
- Con GND en D3 el firmware reporta el modo a 25 fps; ver `docs/FORMATO_TRAMA.md`.

## T5.5 Visor en la PC (2026-10-11)

`tools/viewer.py`: lee las lineas `PMU` del puerto serie (o un log con `--replay`) y grafica en vivo frecuencia,
V rms, I rms, desfase V - I y la bandera de sincronia (en rojo si es NOSYNC, verde SYNC, naranja HOLD); al
terminar imprime tramas, tasa, huecos y recuento por bandera. Con `--duration` y `--save` corre sin ventana y
guarda la figura.

- Aceptacion "grafica en vivo estable 5 min": `python tools/viewer.py --port COM6 --duration 300 --save
  docs/viewer_5min.png` con la senal del DAC (60,300 Hz): **8990 tramas en 299,9 s = 30,0 por segundo, 0 huecos
  mayores a 2,5 periodos** (mayor intervalo entre tramas llegadas 66 ms, por agrupacion del USB), f = 60,300 Hz
  sin deriva (variacion de +-0,003 Hz), V - I = 0 +- 0,015 deg. Figura en `docs/viewer_5min.png`; la de un log
  grabado en `docs/viewer_replay.png`.
- No pude ver la ventana interactiva: la comprobacion con ventana abierta (plt.pause) la hace Luis.

## T1.5 Con antena externa (2026-10-11, tarde)

Luis conecto una antena externa al conector coaxial del modulo (GPS cableado al Nucleo: TXD -> D0, PPS -> A1).

- Vigilancia 7 min por el Nucleo (`tools/fix_watch.py`, `data/t1_5_antena_20261011.csv`): 420 STATE,
  **fix = 0 y sats = 0 en todos**, 0 pulsos PPS.
- Diagnostico UBX (`-DUBX_DIAG`, `tools/ubx_diag.py 30 COM6`; log `data/t1_5_ubx_diag_antena_ext_20261011.{bin,txt}`;
  el log del mismo nombre de la prueba por USB directo, `t1_5_ubx_diag_20261011.*`, quedo sobrescrito por esta
  corrida, sus cifras estan arriba en esta seccion):
  - **SV26 enganchado de forma estable: 29-30 dB-Hz, `code lock` / `code+carrier`, con orbita (efemerides)**
    (antes: un SV a 23-28 dB-Hz que aparecia 2 s cada 15-30 s y nunca se adquiria);
  - otros 3 detectados pero inutilizables: SV2 19 dB-Hz, SV30 15-23 dB-Hz, SV31 18 dB-Hz;
  - MON-HW: antena `OK`, alimentada; `agcCnt` = 2993 (antes 4453-4599), `noisePerMS` 70-97, `jamInd` 9-26/255.
- Lectura: la antena externa mejora la recepcion (de 1 SV intermitente a 1 SV enganchado y 3 detectables), pero
  con 1 SV utilizable el receptor no puede resolver posicion/tiempo (hacen falta 4, o 1 con posicion conocida
  para solo-tiempo). Una vista de cielo abierta suele dar 35-45 dB-Hz y 8+ satelites. Pendiente: ubicar la antena.

## T1.5 Primer fix - CUMPLIDA (2026-10-11)

Antena externa reubicada por Luis. `tools/fix_watch.py`, log `data/t1_5_antena2_20261011.csv` (381 s):
**primer fix a los 34 s** y **fix sostenido 300 s con >= 4 satelites** (5-8 satelites, calidad GGA 1-2; la 2 es
fix diferencial por SBAS). 350 pulsos PPS en 347 s con fix (1 por segundo). Criterio del md cumplido.

## T2.1 Captura del PPS (2026-10-11) - cifras provisionales, ver T2.2

Linea `PPS,<n>,<fase>,<k>,<n_dma>` (k = muestras disparadas hasta el pulso, TIM3 por hardware; k - n_dma = 0 en
los 350 pulsos). Con T = k * 1000 + fase (ticks de 60 MHz nominales) y `tools/analyze_pps.py` sobre el log de arriba
(344 intervalos validos, 0 saltos):

| Medida | Resultado |
|---|---|
| Delta medio entre PPS | **59 932 760 ticks**, es decir el reloj del Nucleo va **-1121 ppm** (59,9328 MHz) |
| Desviacion estandar del delta | **3511 ticks = 58,5 us (58,5 ppm)** |
| Jitter segundo a segundo | 1743 ticks = **29,0 us (29,0 ppm)** |
| Deriva en 6 min | de -1076 a -1190 ppm y de vuelta a -1105 (calentamiento del chip) |

- El criterio del md ("delta ~ frecuencia del timer, variacion de pocas decenas de cuentas") **no se cumple**:
  la variacion es de miles de cuentas. **No es el PPS** (el del NEO-7M tiene ~30 ns rms): es el reloj del Nucleo,
  que va con el oscilador RC interno (HSI). Coincide con el -1029 ppm medido contra la PC en T1.2.
- Consecuencia para el sello de tiempo (T5.1): el reloj varia ~29 ppm entre un segundo y el siguiente. Si el
  tiempo dentro de un segundo se interpola con la tasa del segundo anterior (unica opcion causal), el error de
  sello puede llegar a ~29 us = 0,63 deg = **1,1 % de TVE a 60 Hz**, sobre el limite de la norma. Interpolando con
  la tasa medida del propio segundo (aplazando el reporte hasta el siguiente PPS) baja a ~7 us (0,16 %).
  Con el HSE del ST-LINK (SB4/SB6, opcion A de T1.2) la estabilidad de corto plazo seria del orden de 1 ppm.

## T2.2 Medicion larga del PPS (2026-10-11) - cifras definitivas

`data/t2_2_pps_20261011.csv`, 30 min con fix continuo (5-10 satelites, 1830 STATE y 1830 PPS, `#NMEA bad=0`),
`tools/analyze_pps.py` (figura `docs/pps_30min.png`):

| Medida | Resultado |
|---|---|
| Intervalos validos | 1828 (0 saltos, 1827 s) |
| Delta medio entre PPS | **59 932 410,4 ticks** = frecuencia efectiva del timer 59,93241 MHz |
| **Error del reloj del Nucleo** | **-1126,5 ppm** (ref. GPS, via PPS) |
| Desviacion estandar del delta | **3443 ticks = 57,4 us (57,4 ppm)** |
| Rango (min / max) | 59 920 160 / 59 942 447 ticks (22 287 ticks) |
| Jitter segundo a segundo | **1652 ticks = 27,5 us (27,5 ppm)** |
| Deriva por bloques de 182 s | -1116, -1154, -1138, -1170, -1160, -1108, -1116, -1070, -1089, -1146 ppm |

- Cada cuenta del timer vale 1 / 59,9324 MHz = **16,69 ns**; la dispersion de 3443 cuentas equivale a 57 us.
- La dispersion es del **reloj del Nucleo (HSI)**, no del PPS: el ruido entre segundos y la deriva (+-40 ppm en
  minutos) son tipicos de un oscilador RC. Un PPS de u-blox 7 tiene ~30 ns rms.
- Coincide con T1.2 (-1029 ppm contra la PC) y con la corrida de 6 min (-1121 ppm).
- Implicacion de diseno (ver T2.1): sin HSE, un sello de tiempo causal puede errar ~29 us (1,1 % de TVE a 60 Hz).

## T2.4 Retardo PPS -> NMEA (2026-10-11)

Build `-DNMEA_TS`: la ISR de USART1 sella cada '$' con (k, TIM2->CNT) en la misma linea de tiempo del PPS; el
bucle principal emite `NMEA,<tipo>,<k>,<cnt>,<hora>` por sentencia. `data/t2_4_nmea_20261011.csv`, 10 min con fix,
610 PPS y 5490 sentencias; `tools/analyze_nmea_delay.py` (figura `docs/nmea_delay.png`). Retardo entre el PPS y el
primer byte de cada sentencia, con la frecuencia efectiva del timer (59,933 MHz) del propio log:

| Tipo | n | media (ms) | sigma (ms) | min / max (ms) |
|---|---|---|---|---|
| **RMC** | 609 | **68,75** | 3,45 | 59,6 / 79,8 |
| VTG | 609 | 139,55 | 3,45 | 130,4 / 150,7 |
| **GGA** | 609 | **175,98** | 3,45 | 166,9 / 187,1 |
| GSA | 609 | 258,24 | 3,45 | 249,1 / 269,3 |
| GSV (4 por segundo) | 2436 | 423 | 78,7 | 305 / 548 |
| GLL | 609 | 585,58 | 6,09 | 570 / 607 |

- Orden fijo dentro de cada segundo: RMC, VTG, GGA, GSA, GSV x4, GLL. A 9600 baud una sentencia de ~70 caracteres
  tarda ~73 ms en llegar completa, asi que la RMC completa (y el segundo que etiqueta) se conoce ~140 ms despues
  del pulso y la GGA ~250 ms despues.
- La dispersion de 3,45 ms es **comun a toda la rafaga** (RMC, VTG, GGA y GSA tienen la misma sigma): el modulo
  decide cuando empezar a transmitir con ese jitter. Por eso la hora NMEA solo etiqueta el segundo; el instante lo
  da el PPS.
- **Hipotesis del md confirmada con datos: la RMC posterior al pulso trae la hora de ESE pulso.** Comparando la
  hora de cada RMC con el segundo UTC del reloj de la PC en el instante del pulso (llegada - retardo - 100 ms de
  margen de transmision/USB): diferencia **+0 s en 609 de 609 RMC**. (La referencia es el reloj de la PC, valido
  a +-0,4 s; no puede distinguir +-1 s si la PC estuviera desfasada por un segundo o mas.)
- Regla para T5.1: el pulso k se etiqueta con la hora de la primera RMC recibida en los 200 ms siguientes.

## T2.3 PPS sin fix (2026-10-11)

`data/t2_3_sinfix_20261011.csv`, 900 s, antena tapada por Luis. La obstruccion solo fue efectiva ~15 s (hacia el
segundo 413; el resto del tiempo siguio habiendo 3-8 satelites con fix), pero basta para ver el comportamiento:

| Evento (s desde el inicio) | Satelites / fix | Pulso PPS |
|---|---|---|
| 413 | 6 -> **0**, fix 2 -> 0 | el ultimo pulso es el del propio segundo 413; **ninguno despues** (hueco de **18,5 s**) |
| 428-430 | reaparecen 3-4 satelites, GGA calidad 1 (3 s) y vuelve a 0 | sigue sin pulso |
| **431** | 4 satelites, **GGA fix = 0** | **el pulso vuelve** (3 s despues de reaparecer los satelites) |
| 431-443 | 3-4 satelites, **fix = 0** (13 s) | **pulsos presentes con fix = 0** |
| 444 | fix = 1 | pulsos presentes |
| 142-150 y 457-463 | satelites caen a 0 un instante | huecos de 8 s y 6 s |

- **El PPS desaparece en el mismo segundo en que se pierden todos los satelites**: no hay pulsos libres
  (holdover) en la configuracion por defecto del NEO-7M.
- **El PPS vuelve antes que el fix de la GGA**: de 902 STATE, 859 con fix > 0 (847 con pulso) y 43 con fix = 0
  (**22 con pulso**). El modulo emite el pulso cuando tiene sincronia de tiempo (>= 3 satelites), aunque la GGA
  siga en calidad 0. Por eso **el criterio de sincronia es la presencia y regularidad del PPS, no el campo `fix`**.
- La hora NMEA no cae con los satelites (la mantiene el RTC interno del modulo): una RMC sola **no** prueba
  sincronia (`utc` seguia avanzando durante el hueco).
- Regla propuesta para la bandera (T5.2): SYNC con pulso en el ultimo 1,5 s, intervalo coherente con el anterior
  (+-0,2 %) y hora de RMC recibida para ese pulso; HOLD hasta 5 s sin pulso (extrapolando con la ultima tasa:
  el error crece ~30 ppm/s por el HSI); NOSYNC despues; vuelta a SYNC tras 3 pulsos consecutivos buenos.

## T5.1 / T5.2 Sello UTC y maquina de estados (2026-10-11)

Implementado en `src/main.c`: linea de tiempo comun en ticks (`T = k*1000 + fase`); cada pulso se etiqueta con la
RMC de los 0,5 s siguientes (T2.4); el instante del centro de la ventana de cada reporte se calcula desde el contador
de muestras (retardo de grupo del CIC, 4,5 muestras, compensado) y se interpola desde el ultimo pulso con la tasa del
segundo anterior (causal). Maquina de estados: SYNC (pulso en los ultimos 1,5 s, >= 3 intervalos regulares, etiqueta
confirmada por RMC), HOLD (<= 5 s sin pulso), NOSYNC (resto); regla de T2.3 (el criterio es el PPS, no `fix`).
`utc` con microsegundos: `ddmmyyThhmmss.ffffff`.

- Funciona: `data/t5_sync_20261011.csv` (150 s, GPS con fix, senal del DAC): SYNC a ~1 s del arranque (3 pulsos),
  4468 tramas SYNC / 27 NOSYNC, `gaps = 0`, `labmiss = 0` (la etiqueta predicha coincidio siempre con la RMC),
  UTC del firmware coincide con la PC a 0,43 s (latencia USB). Paso entre tramas 33,3727 ms (sigma 1,9 us).
- **NO cumple la exactitud con el HSI.** La senal del DAC esta fija a la rejilla de muestreo (paso de fase entre
  tramas regular, sigma 0,6 us); el paso entre *sellos* salta en cada pulso porque el sello se vuelve a anclar:
  `tools/check_stamp.py`, 150 fronteras de segundo:

| Medida | Valor |
|---|---|
| Discontinuidad del sello en el pulso (= error acumulado al final del segundo) | sigma **34,0 us**, max **93,6 us** |
| Error al final del segundo, media / p95 | 26,2 us / 73,0 us |
| TVE por tiempo al final del segundo | rms **1,29 %**, max **3,54 %** (limite 1 % = 26,4 us) |
| Segundos cuyo error final supera el limite de 1 % | **43 %** |
| rms sobre todo el segundo (perfil lineal) | 19,6 us = **0,74 %** |

- Causa: el reloj del Nucleo (HSI) cambia su tasa ~24-39 ppm de un segundo al siguiente (T2.2); la interpolacion
  causal usa la tasa del segundo anterior y el error crece linealmente hasta el siguiente pulso. Es el limite de
  usar el oscilador RC como base de tiempo; con HSE (reloj del ST-LINK, SB4/SB6) la estabilidad de corto plazo
  deberia ser ~1 ppm (1 us de error). **Sin HSE el uPMU no cumple el 1 % de TVE en 43 % de los segundos.**
- Nota de metodo: un primer analisis con la fase desenrollada de trama a trama daba residuos de <1 us por error
  mio: esa fase pierde los ciclos enteros (pendiente aliasada de 0,3 Hz) y es ~200 veces menos sensible al sello.
  El resultado correcto es el de la tabla (salto del paso de sello en las fronteras, con el paso de fase como
  referencia).
- La frecuencia reportada estaba en unidades del reloj de muestreo (error de -1126 ppm = 68 mHz a 60 Hz); ahora se
  corrige con la tasa medida por el PPS (`f * tps / reloj_nominal`).
