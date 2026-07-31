# Módulo: mooer_eq

Objetivo: modelar en PC el EQ del **Mooer GE300** y optimizar presets que copien las curvas RC.

## Modelo del pedal

- 5 campanas fijas: **30 / 148 / 735 / 3637 / 18000 Hz**
- Q mostrado fijo: **0.3**
- Gain display: **-16…+16 dB**, paso **0.5 dB**
- Global: rango hardware **−60…+3 dB**, mapeo **1:1** (presets operativos siguen bloqueados en **+3 dB**)
- Calibración (hasheada en `data/CALIBRATION_PROVENANCE.json`):
  - `gain_eff = 0.75 * gain_display` (solo bandas)
  - `Q_eff = 0.3 * (0.569 - 0.0026 * gain_display)`

## Dependencia

Consume curvas reconstruidas de [`../rc_pedals`](../rc_pedals).

## Contenido

| Ruta | Qué es |
|---|---|
| `code/02_multizone_discrete_optimization.py` | Optimización multizona |
| `code/03_constraint_diagnostics.py` | Qué restringe realmente el ajuste |
| `code/04_operational_selection.py` | Selección operativa conservadora |
| `code/05_comparison_by_region.py` | Comparación por regiones |
| `data/final_presets.csv` | Presets finales |
| `data/PRESETS_RECOMENDADOS.json` | Recomendación operativa |
| `docs/00_RESUMEN_EJECUTIVO.md` | Decisión y métricas |

## Presets recomendados

Orden: 30 / 148 / 735 / 3637 / 18000 Hz · Global +3 dB · Q 0.3

| Setup | Gains (dB) |
|---|---|
| Bajo | `[15.0, 3.5, -3.5, 16.0, -3.5]` |
| Híbrido | `[-1.5, 3.0, 4.0, 8.5, 1.5]` |
| Guitarra | `[-10.5, 5.5, 2.0, 10.5, 0.0]` |

## API / CLI

```bash
python modules/mooer_eq/code/mooer_cli.py audit
python modules/mooer_eq/code/mooer_cli.py summarize
python modules/mooer_eq/code/mooer_cli.py evaluate
```

Código reutilizable:

- `mooer_model.py` — modelo GE300 calibrado (`preset_response_db`, `regional_rmse`)
- `mooer_artifacts.py` — carga/evaluación de presets

## Paths

Vía `code/repo_paths.py`:

- Datos/presets: `data/`
- Curvas objetivo: `../rc_pedals/data/refined_curves_192ppo.csv`
- Plots: `plots/`

## Pipeline (orden)

```bash
python modules/mooer_eq/code/02_multizone_discrete_optimization.py
python modules/mooer_eq/code/03_constraint_diagnostics.py
python modules/mooer_eq/code/04_operational_selection.py
python modules/mooer_eq/code/05_comparison_by_region.py
```
