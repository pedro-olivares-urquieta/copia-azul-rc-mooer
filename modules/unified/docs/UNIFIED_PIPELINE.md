# Pipeline unificado

## Etapas ligeras (recomendadas primero)

```bash
python modules/unified/code/cli.py audit
python modules/unified/code/cli.py summarize
python modules/unified/code/cli.py evaluate
python modules/unified/code/cli.py plan
```

## Etapas heavy (requieren audio + deps DSP)

```bash
python modules/emulate_azul/code/build_v10_2.py
python modules/rc_pedals/code/source_reconstruction_pipeline.py --output-dir modules/rc_pedals/_runs/reconstruction
python modules/mooer_eq/code/02_multizone_discrete_optimization.py
python modules/mooer_eq/code/04_operational_selection.py
python modules/mooer_eq/code/05_comparison_by_region.py
python modules/unified/code/cli.py summarize
```

## Contratos entre módulos

| Productor | Artefacto | Consumidor |
|---|---|---|
| `emulate_azul` | `results/CURVAS_DENSAS_V10_2.csv` | `unified` |
| `rc_pedals` | `data/refined_curves_192ppo.csv` | `mooer_eq`, `unified` |
| `mooer_eq` | `data/final_presets.csv` | `unified` |
