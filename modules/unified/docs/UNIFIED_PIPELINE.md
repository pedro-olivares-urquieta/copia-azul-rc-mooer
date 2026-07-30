# Pipeline unificado

## Etapas ligeras (recomendadas primero)

```bash
python modules/unified/code/cli.py audit
python modules/unified/code/cli.py summarize
python modules/unified/code/cli.py evaluate
python modules/unified/code/cli.py plan
```

## Orquestador: Azul (± RC) → Mooer anti-error

```bash
# 1) Mooer copia la curva Café→Azul
python modules/unified/code/cli.py fit-azul

# 2) Cascada Azul+RC modelada solo en Mooer
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose plus

# 3) RC físico ON → Mooer hace el residual (Azul − RC)
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose minus
# Si el nivel global lo maneja otro bloque, preferir forma:
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose minus --timbre-only
```

Salidas en `modules/unified/data/fits/`.

## Etapas heavy (requieren audio + deps DSP)

```bash
python modules/emulate_azul/code/build_v10_2.py
python modules/rc_pedals/code/source_reconstruction_pipeline.py --output-dir modules/rc_pedals/_runs/reconstruction
python modules/mooer_eq/code/02_multizone_discrete_optimization.py
python modules/mooer_eq/code/04_operational_selection.py
python modules/mooer_eq/code/05_comparison_by_region.py
python modules/unified/code/cli.py summarize
python modules/unified/code/cli.py fit-azul
```

## Contratos entre módulos

| Productor | Artefacto | Consumidor |
|---|---|---|
| `emulate_azul` | `results/CURVAS_DENSAS_V10_2.csv` | `unified` (audit + fit) |
| `rc_pedals` | `data/refined_curves_192ppo.csv` | `mooer_eq`, `unified` (fit-azul-rc) |
| `mooer_eq` | `data/final_presets.csv` | `unified` (evaluate) |
| `unified.fit_*` | `data/fits/*_mooer_preset.json` | uso operacional GE300 |
