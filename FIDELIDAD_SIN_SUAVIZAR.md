# Fidelidad Café→Azul sin suavizar (V15)

## Intención

Copiar el Bajo Azul **de forma fiel** con la evidencia que ya tenemos (32 M4A / 16 parejas).  
El suavizado regional y la contracción por fiabilidad (V14 / estilo V3-S) quedan como **diagnóstico**, no como curva de implementación.

```text
eq_observed_detail_db  → lo que muestran las parejas (pair-first, sin smooth)
eq_faithful_db         → detalle + escala de presencia calibrada por RENDER vs Azul
eq_faithful_fit_db     → alternativa continua low-λ (menos shrink a 0)
eq_smooth_diagnostic   → NO implementar
```

## Qué hacemos mejor que V4.1 (sigue vigente)

| Tema | Nosotros |
|---|---|
| PSD | DPSS multitaper |
| F0 | Refine cableado |
| Matching | DP acústico, no solo orden |
| Offsets | Estimados (no ×0.62/0.55/0.85) |
| Repro | Bit-idéntica |
| Validación | Render Café+EQ vs Azul (métrica de copia) |

## Qué sacamos de V4.1 para fidelidad (no para suavizar)

- Pesos: SNR regional, ciclos, AAC, open mask, red, **confianza de matching**, **proximidad tonal**, **energía relativa**, mezcla fase×f (§29)
- Agregación **pair-first** (mediana dentro → entre parejas)
- Separación gain / timbre + neutralidad energética
- Desacuerdo ataque–sustain como diagnóstico (no como aplanador de la EQ)

## Qué no adoptamos para el entregable

- Suavizado regional held-out como curva principal  
- Contracción `EQ × reliability` hacia 0 dB  
- Heurísticas físicas fijas B–E–A  

## Resultado operativo

La métrica de verdad es el **error espectral Café+EQ+gain vs Azul** en bandas críticas (0.5–8 kHz), no el parecido visual a los puntos V4.1.

- `presence_scale` escala la EQ sobre 500 Hz **sin cambiar la forma** (no es un kernel de octavas).
- Gain fiel ≈ −11.7…−12.1 dB (sigue alineado con V4.1 / audio / V12).

### V16 (refino con la misma evidencia)

| Aporte V4.1 / propio | Efecto |
|---|---|
| Gain escalar **por pareja** (§24) antes de la forma | Evita que el nivel de una toma se cuele en la EQ |
| Escala de presencia calibrada solo en `CALIB_PAIRS` | Hold-out real en `HOLD_PAIRS` |
| Bootstrap CI de la curva detalle (sin smooth) | Incertidumbre explícita (anchura mediana ~11 dB → presencia frágil) |
| `CURVA_COPIA_OPERATIVA.csv` | Elige automáticamente el ganador hold-out |

Hold-out crítico (0.5–8 kHz), última corrida:

| Variante | RMSE |
|---|---:|
| **v15_faithful (operativa)** | **~4.09** |
| v16_faithful | ~4.19 |
| v12_energy_neutral | ~5.43 |
| v16_detail (sin escala) | ~5.66 |

V15 sigue siendo la copia operativa; V16 aporta el protocolo honesto y el demean por pareja. En 2630 Hz, V16 detalle→escala cae cerca de V4.1 (+6.9 vs +6.6 dB) sin suavizado regional.

Audios: `renders/FIDELIDAD_V16/ESTEREO_L_COPIA_OPERATIVA_R_AZUL.flac`

## Reproducir

```bash
AZUL_OUT_DIR=modules/emulate_azul/_runs/det_A/results \
AZUL_RENDERS_DIR=modules/emulate_azul/_runs/det_A/renders \
python3 modules/emulate_azul/code/improve_v15.py && \
python3 modules/emulate_azul/code/improve_v16.py
```
