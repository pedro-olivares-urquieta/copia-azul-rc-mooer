# Auto-auditoría de agudos (V21 → V22)

## Qué se sentía raro

La operativa V21 **no** era un shelf suave de presencia: hacía un precipicio.

| Hz | V21 | V20 (ref) | V22 |
|---:|---:|---:|---:|
| 2.5 k | +5.0 | +3.0 | +3.0 |
| 4 k | −0.2 | +3.1 | +0.0 |
| 6 k | −2.8 | +4.1 | −0.5 |
| 8 k | −5.0 | +4.5 | −0.5 |
| 10 k | 0 | 0 | 0 |

- Cliff 2.6→8 kHz: **+10.7 dB** (V21) → **+3.5 dB** (V22)
- Escalón 8→10 kHz: **5.0 dB** → **0.5 dB**

## Causa

1. Tras re-extraer V21, varias parejas fretted dan curvas locas (G_12/C_24/E_12 cliffs >18 dB; C_12 +21 dB en 6–8 kHz).
2. El hold-out eligió `fretted_presence_robust` por RMSE, **sin mirar forma**.
3. El taper duro 8→10 kHz encima de un −5 dB @ 8 kHz sonaba a “cae de golpe”.

## Arreglo V22

- Winsorize ±8 dB en 1.5–10 kHz antes de agregar
- Pesos presencia más apretados
- Soft floor −0.5 dB en 4–8 kHz (no smooth por octavas)
- Carrera con penalización de forma (`shape_bad` si cliff>5 y shelf<−1.5)
- Sigue el air `hard_10k` (15/18 kHz → 0)

Operativa: `v22_winsor_fretted_tight_floor+v22_hard_10k` · gain ≈ −12.94 dB · hold-out ≈ 4.33 dB
