# Fidelidad Café→Azul sin suavizar (V15→V17)

## Intención

Copiar el Bajo Azul **de forma fiel** con la evidencia que ya tenemos (32 M4A / 16 parejas).  
El suavizado regional y la contracción por fiabilidad (V14 / estilo V3-S) quedan como **diagnóstico**, no como curva de implementación.

```text
eq_observed_detail_db  → lo que muestran las parejas (pair-first, sin smooth)
eq_faithful_db         → detalle + escala de presencia calibrada por RENDER vs Azul
CURVA_COPIA_OPERATIVA  → ganador hold-out (V17)
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
- Desacuerdo ataque–sustain / repetibilidad de fase (§29.1) como **peso**, no como aplanador
- Pesos de pareja por confianza de alineación (§31)

## Qué no adoptamos para el entregable

- Suavizado regional held-out como curva principal  
- Contracción `EQ × reliability` hacia 0 dB  
- Heurísticas físicas fijas B–E–A  

## Resultado operativo (V17)

La métrica de verdad es el **error espectral Café+EQ+gain vs Azul** en bandas críticas (0.5–8 kHz), no el parecido visual a los puntos V4.1.

Hold-out crítico (CALIB=`A_12,C_12,E_12,C_chromatic` / HOLD=`B_12,D_12,G_12,C_24`):

| Variante | RMSE hold | bias 2–4 kHz |
|---|---:|---:|
| v15_faithful_recal | **4.131** | +0.69 |
| **v17_v15w_weighted_all (operativa)** | **4.132** | **+0.36** |
| v16_faithful | 4.320 | +0.78 |
| v17 demean-* | ≥4.74 | — |
| v12_energy_neutral | 5.386 | −1.14 |

**Operativa:** `v17_v15w_weighted_all` — misma familia de observaciones que V15 + mediana ponderada por confianza de alineación + repetibilidad de fase; `presence_scale≈0.38`; gain ≈ **−11.99 dB**. Casi empatada en RMSE, pero **mitad de bias en 2–4 kHz**.

El demean por pareja (V16/§24) empeora la copia con estas sesiones; se conserva como diagnóstico.

Archivos:

- `CURVA_COPIA_OPERATIVA.csv` / `GAIN_COPIA_OPERATIVA.csv`
- `IMPLEMENTACION_FIEL_V17.json`
- Audios: `renders/FIDELIDAD_V17/ESTEREO_L_COPIA_OPERATIVA_R_AZUL.flac`
- Unified: `--variant faithful` (o `copy` / `operative`)

## Reproducir

```bash
AZUL_OUT_DIR=modules/emulate_azul/_runs/det_A/results \
AZUL_RENDERS_DIR=modules/emulate_azul/_runs/det_A/renders \
python3 modules/emulate_azul/code/improve_v17.py
```
