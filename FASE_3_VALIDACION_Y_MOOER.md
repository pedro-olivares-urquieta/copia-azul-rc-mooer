# Fase 3 — Curvas por fase, gain profundo, CV ampliada y MOOER trazable

## Qué se cerró

| Hueco del prompt maestro | Entrega |
|---|---|
| §13 Curvas ataque/sustain | `CURVAS_POR_FASE_V13.csv` + alias `CURVA_ATAQUE_*` / `CURVA_SUSTAIN_*` + multiescala |
| §19 Gain multi-estimador + headroom | `GAIN_PROFUNDO_V13.json` / `.csv`, `NIVELES_AUDIO_HEADROOM_V13.csv` |
| §25 LORO / LOPO / LOEO | `VALIDACION_LORO_V13.csv`, `VALIDACION_LOPO_V13.csv`, `VALIDACION_LOEO_V13.csv` |
| §28 Global −60…+3, 1:1 | `MooerModel.global_gain_*` + `global_gain_grid()` |
| §29 Calibración hasheada | `modules/mooer_eq/data/CALIBRATION_PROVENANCE.json` |
| §35 configs multi-módulo | `config/{mooer_eq,rc_pedals,unified}.yaml` |
| §38 Tests | `tests/test_{onsets,mooer_model,gain_estimators,phase_curves}.py` |
| §39 `python -m modules.X` | `__main__.py` en cada módulo |

## Cómo reproducir

```bash
# Sobre un run ya materializado (no pisa results/ publicado):
AZUL_OUT_DIR=modules/emulate_azul/_runs/det_A/results \
AZUL_RENDERS_DIR=modules/emulate_azul/_runs/det_A/renders \
python3 modules/emulate_azul/code/improve_v13.py

python3 -m pytest tests/ -q
python3 -m modules.mooer_eq summarize
```

## Decisiones que no se reabren aquí

- No se regeneran presets Azul+RC (3637 Hz sigue apoyado en una zona 2–4 kHz con N_eff bajo).
- El gain de audio (RMS / true-peak / LUFS proxy) mide la diferencia de instrumento bajo condiciones pareadas; el gain operativo de la EQ sigue siendo el residual de fundamentales (pair-balanced / energy-neutral V12).
- `gain_coeff=0.75` queda declarado con hash; no se “recalibra” sin medición nueva del unidad.
