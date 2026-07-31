# V21 — mejoras aplicadas de las auditorías bajos + agudos

## Aplicado (sin smooth / sin EQ×reliability / sin ×0.62)

| Mejora | Origen | Estado |
|---|---|---|
| Ventana `low` 60–760 ms (min 180 → sustain) | Bajos V4.1 | Sí — mediana ~482 ms |
| Detrend lineal + resta ruido pre-onset | Bajos | Sí en extract |
| `rel_db` vs pico evento (−58/−68/−82) | Bajos | Sí en observaciones |
| `PHASE_MIX` 82%/38% sobre `low` | Bajos | Sí (`improve_v14`) |
| SNR split 350–600 / 600–900 | Bajos | Sí (`improve_v12`) |
| Hum σ=28 cents (50/100/150) | Bajos | Sí |
| Open soft-stop 300 Hz + máscara 280–300 | Bajos | Sí (antes hard-cut; rampa activa) |
| `presence_scale` solo 0.5–8 kHz | Agudos | Sí (`calibrate_presence_scale`) |
| Taper aire → 0 (`v21_hard_10k`) | Agudos | Sí |

## Operativa

- Run: `modules/emulate_azul/_runs/det_v21/`
- `pipeline_version=V21.0-operative`
- `source_variant=v21_fretted_presence_robust+v21_hard_10k`
- Gain ≈ **−12.90 dB** · hold-out crítico ≈ **4.30 dB**
- 15/18 kHz → **0 dB**

### Landmarks (eq_copy)

| Hz | dB | Hz | dB |
|---:|---:|---:|---:|
| 30.9 | −1.50 | 515 | +2.50 |
| 98 | −2.06 | 900 | +1.77 |
| 400 | +4.43 | 2500 | +5.01 |
| 8000 | −4.97 | 15000 | 0.00 |

## Nota

El hold-out de `det_v21` no es comparable 1:1 con `det_A` V20 (re-extracción completa).  
La caída ~−5 dB @ 8 kHz viene de la curva fretted+scale; el aire ya no arrastra presencia.
