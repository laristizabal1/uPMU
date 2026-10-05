# uPMU (STM32)

Proyecto del curso Taller de Potencia (Uniandes, 2026-20). uPMU = micro-PMU (medición de fasores); firmware para STM32.

## Hardware / toolchain (de platformio.ini)
- Placa: ST Nucleo F303K8 (STM32F303K8, Cortex-M4F)
- PlatformIO, plataforma `ststm32`, framework `stm32cube` (HAL/LL de ST, sin Arduino)
- Build: `pio run` — Subir: `pio run -t upload` (la nube no tiene la placa: solo compilar)

## Estado
<!-- TODO(luis): completar antes de subir -->
- Objetivo del firmware: ...
- Hecho hasta ahora: solo el esqueleto PlatformIO (src/ vacío)
- Siguiente paso: ...

## Convenciones
- Código en `src/`, headers en `include/`. Cambios mínimos, sin dependencias nuevas sin motivo.
