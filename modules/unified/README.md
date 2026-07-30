# Módulo: unified

Orquestador de los tres módulos del proyecto:

1. `emulate_azul` — transferencia Café→Azul  
2. `rc_pedals` — respuestas RC (bass/hybrid/guitar)  
3. `mooer_eq` — modelo EQ Mooer GE300 + presets  

## Qué hace

- Audita artefactos de los tres módulos
- Resume curvas Azul, curvas RC y presets Mooer
- Evalúa presets Mooer contra curvas RC
- Muestra el plan de pipeline (ligero vs heavy DSP)
- Escribe reportes en `data/`

## CLI

```bash
python modules/unified/code/cli.py audit
python modules/unified/code/cli.py summarize
python modules/unified/code/cli.py provenance
python modules/unified/code/cli.py evaluate
python modules/unified/code/cli.py plan
python modules/unified/code/cli.py plan --allow-heavy
```

## Salidas

| Archivo | Contenido |
|---|---|
| `data/unified_summary.json` | Resumen cruzado |
| `data/unified_artifact_audit.csv` | Inventario de artefactos |
| `data/pipeline_edges.csv` | Provenance producer→consumer |
| `data/mooer_evaluation.csv` | RMSE regional de presets recomendados |

## Flujo conceptual

```text
audio/cafe_vs_azul ─► emulate_azul ─► curva Café→Azul + gain
audio/rc_response  ─► rc_pedals     ─► curvas RC
rc_pedals curvas   ─► mooer_eq      ─► presets GE300
todo lo anterior   ─► unified       ─► auditoría / resumen
```
