# Observador DC

Plataforma de adquisición, identificación y diagnóstico para accionamientos
de corriente continua operando en lazo cerrado.

## Contenido

- `firmware/` — Firmware STM32F407VG: observador de Kalman, control PI,
  medición M/T, telemetría por DMA
- `src/observador/` — Adquisición, identificación y análisis en Python
- `notebooks/` — Análisis reproducible
- `docs/` — Protocolo de telemetría y documentación técnica

## Instalación

```bash
uv sync --all-extras
```

## Uso

```bash
uv run obs-barrido --puerto COM11
```

## Hardware

STM32F407G-DISC1 · BTS7960 · motor DC con encoder incremental (1266 CPR)

## Licencia

Código propio: MIT. Los drivers HAL en `firmware/Drivers/` están bajo
licencia de STMicroelectronics.