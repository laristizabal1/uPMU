# CLAUDE.md — µPMU portátil (Taller de Potencia 2026-20)

Este archivo lo lee Claude Code al abrir el repo. Mantenerlo corto y actualizado.

## Qué es el proyecto
Prototipo de µPMU (micro unidad de medición fasorial) portátil, para Colombia (60 Hz, 120 V fase-neutro)
y Chile (50 Hz, 220 V fase-neutro). Prototipo: 1 tensión + 1 corriente. Versión final: 3 + 3.
Norma de referencia: IEEE C37.118.1-2011, clase M, estado estable. Metas: TVE <= 1 % (meta interna de
diseño <= 0,2 %), FE <= 5 mHz, RFE <= 0,1 Hz/s (0,01 Hz/s como meta interna).
Idioma de documentación y comentarios: español técnico. Términos técnicos en inglés con traducción la primera vez.

## Hardware disponible (hoy)
- NUCLEO-F303K8 (STM32F303K8T6, Cortex-M4F, 12 KB SRAM + 4 KB CCM sin acceso por DMA, dos ADC de 12 bit,
  DAC1 con 2 canales y DAC2 con 1, TIM2 de 32 bit). Sin cristal: reloj HSI (8 MHz) con PLL, máximo 64 MHz.
  El MCO del ST-LINK como HSE exige cambiar puentes (SB); NO asumirlo.
- ESP32-S3-DevKitC (pasarela por SPI, emulador de GPS: PPS + NMEA, registrador). NO tiene DAC y NO se usa como ADC.
- Llegarán más adelante: módulos ZMPT101B (tensión), ZMCT103C (corriente), módulo GPS NEO-6M.

## Cadena de medición (decisiones vigentes; cambiarlas solo con evidencia)
sensor -> acondicionamiento (punto medio 1,65 V, RC anti-aliasing fc ~ 5 kHz) -> ADC1/ADC2 simultáneos disparados
por temporizador (DMA, doble búfer en SRAM principal) -> decimación x4 con CIC de orden 3 -> estimador
(IpDFT con ventana Hann de 4 ciclos; candidata: i-IpDFT de 3 ciclos) -> sello de tiempo UTC con el PPS capturado
por TIM2 (32 bit) -> reporte (C37.118.2 o formato propio) hacia el ESP32-S3.
- Objetivo con cristal: 60 kS/s -> 15 kS/s. Con HSI (64 MHz) provisional: 64 kS/s -> 16 kS/s.
- Presupuesto de TVE en cuadratura: sensor 0,12 %, ADC 0,04 %, sincronización 0,05 %, algoritmo 0,10 %.
- Escala de entrada: pico nominal <= 1,375 V en tensión y <= 0,825 V en corriente (cubre 120 % y 200 %).
- Tasa de reporte: 60 tramas/s (Colombia) y 50 (Chile); 10 como tasa común secundaria.
- Pines propuestos (confirmar en la hoja de datos): A0 = tensión (ADC1_IN1), A3 = corriente (ADC2_IN1),
  PA9 = PPS (TIM2_CH3, AF10), PA10 = NMEA (USART1_RX), SPI1 (D10-D13) hacia el ESP32-S3.

## Reglas de trabajo (importantes)
1. NO inventar cifras ni especificaciones. Si algo no está en un documento del repo (docs/) o no se midió,
   escribirlo como "no verificado". Etiquetar la evidencia: M medición, F fabricante, S simulación,
   A afirmación sin evidencia, N norma, C cálculo propio.
2. Todo algoritmo se desarrolla primero en Python (sim/), con vectores de prueba de referencia ("golden vectors"),
   y solo después se porta a C. El C debe reproducir el Python dentro de una tolerancia documentada.
3. Modularidad: la adquisición NO depende de la comunicación. Si el ESP32-S3, el GPS o un canal fallan, el firmware
   sigue midiendo y marca la trama como inválida o no sincronizada (bandera), nunca como válida.
4. Con amplitud menor a un umbral, el ángulo se marca inválido (no reportar un ángulo sin sentido).
5. Cada cambio de parámetro (Fs, ventana, escala, filtros) actualiza el presupuesto en docs/presupuesto.md.
6. Un cambio = un commit pequeño con mensaje descriptivo. Correr los tests antes de cada commit.
7. Cualquier dato de un artículo o norma debe indicar su fuente y si es especificación o medición.
8. Seguridad eléctrica: ningún procedimiento con red sin transformador de aislamiento, variac, fusible y presencia
   del profesor. Este repo es solo software/documentación; no dar instrucciones de energización sin esas condiciones.

## Estructura del repo
- sim/          simulación en Python: generador de señales de prueba C37.118.1, estimadores, métricas (TVE, FE, RFE)
- sim/tests/    pruebas con pytest
- firmware/     proyecto STM32 (PlatformIO o CMake): src/, include/, test/
- esp32/        firmware del ESP32-S3 (PPS/NMEA, registrador)
- tools/        scripts de PC: generador/validador de tramas C37.118.2, visor serie, captura de datos
- docs/         notas, presupuesto de error, decisiones, bitácora de mediciones
- data/         capturas y vectores de prueba (no subir archivos grandes)

## Comandos (ajustar al montar el entorno)
- Python: `python -m venv .venv && source .venv/bin/activate && pip install numpy scipy matplotlib pytest`
- Tests de simulación: `pytest sim/tests -q`
- Firmware (PlatformIO, verificar el id de placa con `pio boards f303k8`): `pio run -d firmware`, `pio run -d firmware -t upload`
- Monitor serie: `pio device monitor -b 115200`

## Estilo
- C: C11, sin asignación dinámica, tipos de ancho fijo, constantes con unidades en el nombre (por ejemplo `FS_ADC_HZ`).
- Python: tipado, funciones puras, semillas fijas en pruebas aleatorias.
- Documentar cada archivo con su propósito en la primera línea.

## Definición de terminado (para cada tarea)
Código + prueba que lo valida + resultado numérico registrado en docs/ + commit.
