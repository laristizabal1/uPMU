# PLAN.md — qué hacer, en orden (solo con la NUCLEO-F303K8 y el cable USB)

Cada fase tiene: objetivo, tareas, criterio de aceptación y un prompt sugerido para Claude Code. Trabajar una fase a la vez. No saltar a la siguiente sin cumplir el criterio.

## Sobre generadores de señal (decisión)

- **ESP32-S3 como generador de señales: no.** El ESP32-S3 no tiene DAC (verificar en su hoja de datos) y con PWM + filtro RC la exactitud no sirve para caracterizar. Úsenlo para: (1) emular el GPS (PPS de 1 Hz + NMEA), (2) registrar y mostrar datos. Su cristal de 40 MHz es de ±10 ppm: sirve como referencia de tiempo estable, no como UTC.
- **Señal de prueba para desarrollo:** el DAC de la propia Nucleo (DAC1 y DAC2, 12 bit), generando un seno con un acumulador de fase (DDS) disparado por el mismo temporizador del ADC. Como la señal generada se conoce exactamente, se puede calcular el TVE de lazo cerrado. Sirve para desarrollo y regresión, NO para certificar: los errores del DAC y del ADC quedan mezclados.
- **Generador de laboratorio:** sí, para la caracterización de sensores y de TVE (cuando lleguen los módulos). Verificar antes: exactitud de amplitud y fase, y si tiene entrada o salida de sincronía de 1 Hz. No comprar uno.

## Fase 0 — Entorno (media hora)

**Objetivo:** compilar, cargar y ver texto por el puerto serie.

Tareas:
1. Instalar git, Python 3.11 o superior, PlatformIO (CLI) y los drivers del ST-LINK. Crear el repo con la estructura de CLAUDE.md y copiar CLAUDE.md y PLAN.md a la raíz.
2. Firmware mínimo: parpadear LD3 (PB3) e imprimir "hola" a 115200 baudios por el puerto serie virtual del ST-LINK.
3. Reloj: HSI + PLL a 64 MHz y comprobarlo con el temporizador.

**Aceptación:** el LED parpadea a la frecuencia pedida y el monitor serie muestra texto.

**Prompt:** "Lee CLAUDE.md y PLAN.md. Crea la estructura del repo, un proyecto PlatformIO para la NUCLEO-F303K8 (verifica el id de placa con `pio boards f303k8`) que parpadee LD3 y escriba por USART2 a 115200, y deja el reloj en 64 MHz con HSI + PLL. No inventes pines: confirma en la hoja de datos DS9866 y en UM1956 y dime lo que no puedas verificar."

## Fase 1 — Simulación en Python (no necesita hardware; la más valiosa ahora)

**Objetivo:** decidir ventana, tasa de reporte y márgenes con números.

Tareas:
1. Generador de señales: seno con amplitud, fase y frecuencia; desvío de frecuencia ±5 Hz; armónicos (hasta el 50.º al 10 %); interferencia fuera de banda (|f − f0| ≥ Fs/2); modulación, rampa y escalón (después).
2. Modelo de la cadena: ruido, offset y ganancia; RC de 5 kHz (con su fase); cuantización de 12 bit; muestreo a 60 y 64 kS/s; CIC de orden 3 con R = 4.
3. Estimadores: IpDFT con Hann de 4 ciclos y mínimos cuadrados; i-IpDFT de 3 ciclos (Derviškadić, Romano, Paolone); RFE por diferencia simple frente a regresión lineal.
4. Métricas: TVE, FE, RFE, y tablas por prueba y por Fs (10, 25, 50 y 60).

**Aceptación:** la IpDFT de 4 ciclos pasa el estado estable (TVE ~ 0,2 %) y falla fuera de banda, como en la literatura (Delle Femine 2019: 2,7 % de TVE y 854 mHz de FE); la tabla de resultados queda en docs/.

**Prompt:** "Implementa en sim/ el generador de señales de prueba de C37.118.1 clase M, el modelo de la cadena de medición y los estimadores IpDFT (Hann, 4 ciclos) e i-IpDFT (3 ciclos). Calcula TVE, FE y RFE y escribe pruebas con pytest. Reporta una tabla por prueba y por Fs. Marca como 'no verificado' cualquier parámetro que no esté en docs/."

## Fase 2 — Adquisición en el firmware

**Objetivo:** muestrear a tasa fija con dos ADC en simultáneo y sin perder muestras.

Tareas:
1. ADC1 + ADC2 en modo dual simultáneo (confirmar en RM0316), disparados por un temporizador, DMA a doble búfer en la SRAM principal (no en CCM). Tasa provisional: 64 kS/s (ARR = 1000 a 64 MHz).
2. Medir con TIM2 el periodo real entre interrupciones (fluctuación) y los ciclos de CPU con el contador DWT.
3. Caracterizar el ADC sin cables: leer VREFINT miles de veces y obtener ruido (LSB RMS) y una estimación del ENOB.
4. Decimación CIC x4 a 16 kS/s.

**Aceptación:** ni una muestra perdida en 10 min; ruido del ADC registrado en docs/presupuesto.md.

**Prompt:** "Configura ADC1 y ADC2 en modo dual simultáneo disparado por un temporizador, con DMA a doble búfer en la SRAM principal, a 64 kS/s. Verifica en RM0316 cada registro y dime lo que no puedas confirmar. Añade un contador de muestras perdidas y una medición de ciclos con DWT."

## Fase 3 — Señal de prueba con el DAC y lazo cerrado

**Objetivo:** probar la cadena con un seno conocido, sin generador externo.

Tareas:
1. DDS en firmware (acumulador de fase de 32 bit y tabla de seno con interpolación) que escribe en el DAC con el mismo temporizador del ADC. Permite frecuencia distinta de la nominal, armónicos e interferencias.
2. Cableado propuesto (confirmar en la hoja de datos): DAC1_OUT2 (PA5 = A4) a A0 (ADC1_IN1) y DAC2_OUT1 (PA6 = A5) a A3 (ADC2_IN1). Salida del DAC centrada en 1,65 V con amplitud ≤ 1,3 V.
3. Calcular el fasor teórico a partir del estado del DDS y comparar con la medición: TVE de lazo cerrado.

**Aceptación:** se reproduce la simulación de la fase 1 con ruido y errores del DAC incluidos; las diferencias se explican.

**Prompt:** "Implementa un DDS en firmware que genere un seno en el DAC con el mismo temporizador del ADC. Añade un modo de prueba por UART para fijar frecuencia, amplitud y fase, y un cálculo del fasor teórico. Cablea DAC a ADC según PLAN.md."

## Fase 4 — Estimador en el microcontrolador

**Objetivo:** el mismo algoritmo de Python, corriendo en la Nucleo.

Tareas:
1. Portar el estimador elegido en la fase 1 a C (float, FPU). Memoria: acumular solo los bins de la DFT por ciclo (con seis canales no caben ventanas completas en 12 KB).
2. Vectores de referencia: enviar por UART muestras sintéticas generadas en Python, procesarlas en la Nucleo y comparar el fasor, la frecuencia y el ROCOF con los de Python.
3. Medir tiempo de cálculo por trama (DWT) y presupuestar memoria.

**Aceptación:** diferencia con Python dentro de la tolerancia pactada (por ejemplo, 0,01 % de TVE) y cálculo por trama mucho menor al periodo de reporte.

**Prompt:** "Porta el estimador de sim/ a firmware en C sin asignación dinámica. Crea un modo de prueba que reciba por UART un vector de muestras y devuelva fasor, frecuencia y ROCOF, y un script en tools/ que compare con Python."

## Fase 5 — Tiempo: PPS, NMEA y ESP32-S3

**Objetivo:** sello de tiempo con captura por hardware.

Tareas:
1. Captura de PPS con TIM2 en PA9 (TIM2_CH3, AF10), desenvolviendo el contador de 32 bit; medir el periodo real y la deriva del reloj; bandera de pérdida de PPS (retención).
2. Analizador de NMEA por USART1 (PA10), validando checksum.
3. ESP32-S3: emular GPS (PPS de 1 Hz por temporizador de hardware + NMEA a 9600 baudios) para probar la captura y la deriva del HSI (se espera una diferencia grande frente a un cristal).
4. Corrección del ángulo con el desfase entre el PPS y la muestra.

**Aceptación:** histograma de la captura del PPS durante ≥ 1 h; bandera de no sincronizado al desconectar el PPS.

## Fase 6 — Reporte y enlace

Tareas: leer C37.118.2 (conseguirlo en la biblioteca; no está en el material), implementar el generador y el validador de tramas en tools/ (CRC-CCITT), enlace SPI hacia el ESP32-S3 y visor en el PC.

**Aceptación:** una trama válida de 1 tensión + 1 corriente que el validador acepta.

## Cuando lleguen los sensores y el GPS

- Plan A/B del módulo ZMPT101B: prueba de 2 horas (fase a varias amplitudes, calentamiento, día siguiente, barrido de frecuencia).
- Calibración por tablas de fase y ganancia contra una referencia registrada al mismo tiempo (DAQ de 16 bit o equivalente).
- Pruebas de la matriz de LOCO/Löper: 6 s por punto, amplitud 10–200 % en pasos de 10 %, ángulo en pasos de 0,3 rad, frecuencia en pasos de 0,1 Hz.
- Todo con transformador de aislamiento, variac, fusible y el profesor presente.

## Fuera de la terminal (esta semana)

- Pedir en la biblioteca: IEEE C37.118.2-2011, IEEE C37.118.1a-2014, IEC/IEEE 60255-118-1:2018, IEEE C37.242.
- Preguntar si el generador del laboratorio tiene sincronía de 1 Hz y qué exactitud de amplitud y fase declara.
- Comprar según uPMU_BOM_prototipo.xlsx.

## Riesgos abiertos

- Reloj de 64 MHz con HSI: la tasa de muestreo de 60 kHz no es exacta; trabajar con 64/16 kS/s hasta tener cristal.
- Memoria: 12 KB de SRAM limitan la versión de 3 + 3.
- La fase calibrada de los sensores no está publicada: medirla es prioritario.
- El texto de las normas 2014 y 2018 no se ha leído: los límites de RFE y de fuera de banda son de fuentes secundarias.
