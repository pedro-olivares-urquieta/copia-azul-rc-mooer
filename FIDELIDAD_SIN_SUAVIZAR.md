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

## Resultado operativo (V19 presencia + V20 aire)

La métrica de verdad es el **error espectral Café+EQ+gain vs Azul** en bandas críticas (0.5–8 kHz), no el parecido visual a los puntos V4.1.

Hold-out crítico (CALIB=`A_12,C_12,E_12,C_chromatic` / HOLD=`B_12,D_12,G_12,C_24`):

| Variante | RMSE hold | bias 2–4 kHz | 15 kHz |
|---|---:|---:|---:|
| **V19+`v20_hard_10k` (operativa)** | **4.100** | **+0.056** | **0.0** |
| V19 sin taper aire | 4.100 | +0.056 | +3.77 |
| v17_v15w_weighted_all | 4.132 | +0.36 | ~+4.4 |
| v12_energy_neutral | 5.386 | −1.14 | ~+1 |

**Operativa:** presencia robusta V19 + **aire → 0 dB sobre 10 kHz** (fade 8–10 kHz). Gain ≈ **−12.01 dB**.  
Detalle: `ANALISIS_PRESENCIA_BRILLO_AIRE_V41.md`.

### Por qué la presencia “se sentía débil”

No era un EQ globalmente bajo: el bias mediano tras V17 ya era ~0 dB. El problema era **desacuerdo entre parejas** (E_12/B_12 muy brillantes, C_24/D_12 opacos). V19 baja outliers en 1.5–6.5 kHz.

### 15–18 kHz: sí nos pasamos

`presence_scale` ≥500 Hz dejaba +3.7 dB hasta 18 kHz. V4.1 lo trata como diagnóstico (AAC→0). V20 lo corrige **sin** suavizar presencia.

### V18 — qué se probó y qué no mejoró la copia

Con las **mismas 16 parejas**, se adoptaron del informe V4.1 palancas que aún faltaban:

| Idea | Resultado en hold-out |
|---|---|
| §27–29 phase-first (curvas por fase → mezcla §29) | RMSE ~4.76–4.84 (peor) |
| §26 confianza evento (note_error/lag/overlap) | RMSE ~4.57 (peor que V17) |
| §13–16 peso residual narrow→strong | ningún residual gana a V17 |
| §43–45 modos de gain residual | non-open / grid no ayudan |
| Híbrido V17×phase-first | RMSE ≥4.69 |
| Escalas locales 1–2 kHz / 2–4 kHz (nested CV) | RMSE casi igual, **bias peor** |

Conclusión V18: más agregadores V4.1 no bastaban. V19 sí mejoró al atacar el desacuerdo de presencia.

Archivos:

- `CURVA_COPIA_OPERATIVA.csv` / `GAIN_COPIA_OPERATIVA.csv` (**V19**)
- `IMPLEMENTACION_FIEL_V19.json`, `PESOS_PRESENCIA_ROBUSTOS_V19.csv`
- Audios: `renders/FIDELIDAD_V19/`
- PDF: `INFORME_COPIA_AZUL_FIEL.pdf`
- Unified: `--variant faithful`

## Reproducir

```bash
AZUL_OUT_DIR=modules/emulate_azul/_runs/det_A/results \
AZUL_RENDERS_DIR=modules/emulate_azul/_runs/det_A/renders \
python3 modules/emulate_azul/code/improve_v19.py && \
python3 -m modules.unified informe --mode fidelity
```
