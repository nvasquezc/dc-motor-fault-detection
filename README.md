# Closed-loop fault dataset and detection for DC motor drives

Acquisition, identification and diagnosis platform for DC drives operating
**inside a closed control loop**, producing a reproducible fault dataset
with severity expressed in physical units.

> **Status:** firmware and acquisition platform operational. Dataset
> collection in progress. Classifier evaluation pending.

---

## Why this exists

Public datasets for DC motor fault diagnosis are typically recorded
**open-loop** and label severity **categorically** — healthy, degraded,
faulty. Two consequences follow:

**Closed-loop masking.** A feedback controller compensates for incipient
faults, suppressing exactly the signatures a detector must find. A rise in
armature resistance produces a speed error that the PI loop absorbs by
increasing duty cycle. The fault becomes visible in the *control effort*,
not in the *output*. Open-loop data cannot capture this, yet closed-loop
operation is the condition under which every real drive runs.

**Non-transferable labels.** Categorical severity cannot be mapped to
physical units, so a threshold tuned on one dataset means nothing on
another test bench. Reported detection accuracy is not comparable across
studies.

This work records faults inside the control loop, parameterizes severity in
physical units, and publishes the injection procedure so the benchmark can
be rebuilt on comparable hardware.

---

## Approach

The drive is modeled as a first-order system whose input-referred
disturbance absorbs everything the nominal model does not explain:

    w[k+1] = (1-a)·w[k] + b·(u[k] - d[k])

A two-state Kalman filter runs on-target, jointly estimating angular speed
`w` and the input-referred disturbance `d`. Process noise on `d` is set an
order of magnitude below that of `w`, so the filter treats disturbance as a
slowly-varying quantity and separates degradation from ordinary transients.

**The disturbance estimate — not the raw speed signal — carries the
diagnostic information.** Under closed-loop control a rising fault is
absorbed by the PI loop and largely disappears from the speed output, but
it persists in `d_hat`.

`d_hat` is a lumped quantity: it does not attribute degradation to a
specific physical parameter. The contribution is therefore the mapping
between **physically measured injected severity** and the observer
response, characterized across operating points, rather than direct
parameter identification.

Speed is measured with the M/T method: pulse counting loses resolution at
low speed and period measurement loses it at high speed, and fault
signatures appear across the full operating range. Edge timestamps come
from hardware capture, so interrupt latency does not enter the measurement.

---

## System

| Layer | Implementation |
|---|---|
| Board | STM32F407G-DISC1 (STM32F407VG, Cortex-M4F @ ⟨f⟩ MHz) |
| Power stage | BTS7960 H-bridge |
| Speed sensing | Incremental encoder, 1266 CPR, M/T method |
| Current sensing | ⟨sensor⟩ |
| Control | PI speed loop @ ⟨rate⟩ Hz |
| Estimation | EKF @ ⟨rate⟩ Hz, ⟨n⟩ states |
| Telemetry | DMA to UART, ⟨baud⟩ baud, ⟨n⟩ channels @ ⟨rate⟩ Hz |
| Host | Python acquisition, identification and analysis |

The M/T method is used for speed measurement because pure pulse-counting
loses resolution at low speed and pure period-measurement loses it at high
speed. Since fault signatures appear across the full operating range,
neither alone is sufficient.

---

## Experimental design

⟨k⟩ severity levels × ⟨m⟩ operating points × ⟨r⟩ repetitions.

Operating points span ⟨range⟩ so that detection performance can be reported
as a function of load and speed rather than as a single aggregate number.
Repetitions allow run-to-run variability to be separated from fault effect.

---

## Repository layout


---

## Install

```bash
uv sync --all-extras
```

## Run

```bash
uv run obs-barrido --puerto COM11
```

Firmware: open `firmware/observer-mx/` in STM32CubeIDE, build, and flash to
an STM32F407G-DISC1. The debug configuration is versioned alongside the
project.

---

## Citing

Use the "Cite this repository" button, or see [`CITATION.cff`](CITATION.cff).

## License

Own code: MIT. HAL drivers under `firmware/observer-mx/Drivers/` are
licensed by STMicroelectronics.