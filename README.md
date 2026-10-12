# uPMU

Micro-PMU (unidad de medición fasorial) de bajo costo para el curso Taller de Potencia (Uniandes, 2026-20).
Un canal de tensión (ZMPT101B) y uno de corriente (SCT013-100) sobre un **STM32F303K8** (NUCLEO-F303K8),
sincronizado con un **GPS NEO-7M** (PPS). Objetivo: IEEE C37.118.1-2011 clase M, TVE ≤ 0,2 % interno
(límite de la norma 1 %), a 60 Hz / 120 V (Colombia) y 50 Hz / 220 V (Chile).

## Estructura

| Carpeta | Contenido |
|---|---|
| [`STM32/uPMU/`](STM32/uPMU) | Firmware (PlatformIO, C), herramientas de la PC, vectores de prueba, logs de medición y documentación de resultados |
| [`uPMU_AFE/`](uPMU_AFE) | Front-end analógico: esquemáticos, netlists de LTspice y simulación de la cadena completa. Informe: [`RESULTADOS_LTspice.pdf`](uPMU_AFE/docs/RESULTADOS_LTspice.pdf); guía de uso y montaje: [`GUIA_front_end.pdf`](uPMU_AFE/docs/GUIA_front_end.pdf) |
| `Paper/` | Artículos de referencia (PDF de terceros): **solo local, no se versiona** |

Dentro de `STM32/uPMU`: `src/` y `include/` (firmware), `tools/` (scripts Python), `data/` (logs crudos y
`vectors/`), `docs/` (`RESULTADOS.md`, `FORMATO_TRAMA.md`), `ref/` (copia de solo lectura de la simulación de
referencia, con el modelo anterior al del informe de LTspice).

Dentro de `uPMU_AFE`: `codigo/` (scripts), `netlists/` (los `.cir` y el `.asc` de LTspice),
`figuras/` (PNG), `resultados/` (salidas) y `docs/` (informes y hojas del esquemático, en PDF).

## Cadena de medición

```
red -> sensor -> burden -> filtro RC -> ADC 12 bit dual a 60 kS/s (TIM2 + DMA)
    -> CIC orden 3, R = 4 (entero) -> ventana de 4 ciclos -> IpDFT (Hann) + mínimos cuadrados -> fasor
PPS (GPS) -> contador de disparos por hardware (TIM3) -> sello UTC y estado SYNC / HOLD / NOSYNC
```

Salida por el puerto serie virtual (115200): `PMU,<utc>,<f_Hz>,<V_rms>,<V_ang>,<I_rms>,<I_ang>,<bandera>`
a 30 reportes/s (60 Hz) o 25 reportes/s (50 Hz). Formato completo en
[`STM32/uPMU/docs/FORMATO_TRAMA.md`](STM32/uPMU/docs/FORMATO_TRAMA.md).

## Estado

Todas las cifras, con fecha, condiciones y log, están en
[`STM32/uPMU/docs/RESULTADOS.md`](STM32/uPMU/docs/RESULTADOS.md).

- **Hecho y medido:** reloj, GPS por UART con parser NMEA, PPS (captura exacta), ADC dual a 60 kS/s sin pérdidas,
  ruido del ADC (≈ 0,6 LSB rms), CIC entero idéntico al de Python, estimador en el microcontrolador, cadena en vivo
  a 30/25 fps validada con una señal conocida, selector 50/60 Hz y visor.
- **TVE del firmware frente a la simulación** (14 vectores, 2 redes × 7 escenarios): diferencia ≤ 0,00014 %;
  peor TVE 0,0126 % (V) y 0,121 % (I).
- **Limitación abierta:** con el oscilador interno (HSI) el reloj cambia ~25-40 ppm de un segundo a otro y el sello
  de tiempo causal llega a decenas de µs (43 % de los segundos superan 1 % de TVE). Solución en curso: reloj
  externo estable en D7/D8 (`-DUSE_HSE -DHSE_XTAL`, ya soportado por el firmware con respaldo a HSI).
- **Pendiente:** armar y calibrar el front-end real (desfase de ZMPT101B y SCT013, calibración de 1 punto) y
  repetir las mediciones de sincronía con el reloj externo.

## Uso rápido

```bash
cd STM32/uPMU
pio run -t upload                                   # firmware normal (reloj interno)
PLATFORMIO_BUILD_FLAGS="-DUSE_HSE -DHSE_XTAL" pio run -t upload   # con cristal de 8 MHz en D7-D8
python tools/verify_all.py COM6                     # regresion: 14 vectores contra la simulacion
python tools/viewer.py --port COM6                  # visor en vivo
```

Las pruebas en la PC compilan el mismo C del firmware (`tools/test_*.py`, compilador `gcc`/`cc` o
`pip install ziglang`).

El detalle del cableado y de los puertos usados en las mediciones está en `docs/RESULTADOS.md`.
