# Formato de la trama de salida (T5.4)

Línea ASCII por el puerto serie virtual del ST-LINK (USART2, 115200 8N1), terminada en `\r\n`. El formato
IEEE C37.118.2 queda para cuando haya señal real (CLAUDE.md §6, T5.4).

## Línea `PMU` (una por ventana)

```
PMU,<utc>,<f_Hz>,<V_rms>,<V_ang_deg>,<I_rms>,<I_ang_deg>,<bandera>
```

| Campo | Unidad | Decimales | Significado |
|---|---|---|---|
| `utc` | `ddmmyyThhmmss.ffffff` | µs | Instante UTC del **centro** de la ventana (retardo de grupo del CIC compensado). **Vacío** con `NOSYNC`. |
| `f_Hz` | Hz | 4 | Frecuencia (IpDFT + mínimos cuadrados, T4.3): promedio de V e I ponderado por la energía de cada canal, y con el error del reloj de muestreo corregido por la tasa medida con el PPS (`f · tps / reloj_nominal`) cuando hay `SYNC` o `HOLD`. |
| `V_rms` | V rms de red | 3 | Módulo del fasor de tensión, referido a la red (deshace la H nominal del front-end y la ganancia del CIC). |
| `V_ang_deg` | grados, (-180, 180] | 3 | Ángulo del fasor de tensión **en el centro de la ventana**. |
| `I_rms` | A rms | 4 | Módulo del fasor de corriente. |
| `I_ang_deg` | grados, (-180, 180] | 3 | Ángulo del fasor de corriente en el centro de la ventana. |
| `bandera` | texto | — | Estado de sincronía, ver abajo. |

El ángulo de tensión menos el de corriente es el desfase V-I físico. Con `kappa` (calibración de 1 punto del
front-end, CLAUDE.md §8) en 1 todavía no hay corrección de los desfases reales de ZMPT101B y SCT013.

### Banderas

| Bandera | Significado | Estado |
|---|---|---|
| `NOSYNC` | Sin PPS válido (o aún sin 3 pulsos regulares y una RMC que etiquete): `utc` vacío. **Nunca se marca como válida.** | implementada |
| `SYNC` | Pulso en el último 1,5 s, ≥ 3 intervalos regulares seguidos (±0,3 %) y etiqueta confirmada por una RMC; `utc` válido. | implementada |
| `HOLD` | Estaba en `SYNC` y no llega pulso (≤ 5 s): se extrapola con la última tasa; `utc` presente pero **degradado** (el reloj varía ~30 ppm/s con el HSI). | implementada |

El criterio de sincronía es el **PPS**, no el campo `fix` de la GGA: el módulo emite el pulso con ≥ 3 satélites aunque la
GGA siga en calidad 0, y la hora NMEA no cae al perder satélites (T2.3). **Exactitud del sello:** con el reloj interno
(HSI) el error causal llega a decenas de µs (T5.1: σ 34 µs al final del segundo; 43 % de los segundos superan el 1 % de
TVE); con el reloj de 8 MHz del ST-LINK (`-DUSE_HSE`, SB4/SB6) se espera ~1 µs. Ver `docs/RESULTADOS.md`.

## Cadencia

| Red | Ventana | Reportes | Periodo |
|---|---|---|---|
| 60 Hz (selector PB0 abierto) | 4 ciclos = 1000 salidas a 15 kS/s (66,7 ms) | **30 por segundo** | 33,3 ms |
| 50 Hz (selector PB0 a GND) | 4 ciclos = 1200 salidas a 15 kS/s (80 ms) | **25 por segundo** | 40 ms |

Las ventanas se solapan (cada reporte avanza media ventana). Un reporte se omite (no sale línea) si el estimador
no llegó a tiempo o si la ventana fue pisada por muestras nuevas; el firmware lo cuenta en `#LIVE`.

## Otras líneas del mismo puerto

| Línea | Cuándo | Contenido |
|---|---|---|
| `STATE,<ddmmyy>T<hhmmss.ss>,<fix>,<sats>` | 1 por segundo (GGA del GPS) | Hora/fecha del GPS, calidad de fix y satélites |
| `ADC,<n>,<muestras>,<delta>,<ovr>,<proc_ovr>,<tx_drop>,<A m/min/max/std>,<B m/min/max/std>` | 1 por segundo | Estadística del ADC (LSB) y contadores de pérdida |
| `PPS,<n>,<fase>,<k>,<n_dma>` | por cada pulso en PA1 | Fase (ticks de 60 MHz, 0..999) y muestras disparadas hasta el pulso |
| `#NMEA,ok=,bad=` / `#LIVE,f0=,reports=,skipped=,invalid=,cycles=` | cada 10 s | Contadores de integridad |
| `#MODE,f0=` | al cambiar el selector | Modo 50/60 Hz activo |
| `VEC`, `CIC`, `EST`, `MEM` | respuesta a un vector de prueba | Ver `tools/send_vector.py` |

Las líneas que empiezan con `#` son diagnósticos y no deben interpretarse como mediciones.
