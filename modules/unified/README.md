# Módulo: unified

Orquestador de los tres módulos del proyecto:

1. `emulate_azul` — transferencia Café→Azul  
2. `rc_pedals` — respuestas RC (bass/hybrid/guitar)  
3. `mooer_eq` — modelo EQ Mooer GE300 + presets  

## Qué hace

- Audita artefactos de los tres módulos
- Resume curvas Azul, curvas RC y presets Mooer
- Evalúa presets Mooer contra curvas RC
- **Encaja curvas Azul (± RC) en un EQ Mooer anti-error**
- Muestra el plan de pipeline (ligero vs heavy DSP)
- Escribe reportes y fits en `data/`

## Orquestación Azul → Mooer

```text
                    ┌─ fit-azul ──────────────────► Mooer ≈ curva Azul
curva Café→Azul ────┤
                    └─ fit-azul-rc --compose plus ─► Mooer ≈ Azul + RC
                       fit-azul-rc --compose minus ► Mooer ≈ Azul − RC
                                                    (residual si el RC ya está ON)
```

| Comando | Target | Cuándo usarlo |
|---|---|---|
| `fit-azul` | curva Azul (+ gain) | Copiar el Azul solo con el GE300 |
| `fit-azul-rc --compose plus` | Azul + RC | Simular Azul y el boost RC dentro del Mooer |
| `fit-azul-rc --compose minus` | Azul − RC | RC físico ya en cadena; Mooer aporta el residual |
| `… --compose minus --timbre-only` | forma Azul − RC | Preferido si el nivel (−10.6 dB) lo maneja otro bloque; con gain el residual satura el GE300 |

Objetivo anti-error (igual que el histórico de `mooer_eq`):

`worst + 0.35·avg + 0.10·global + 0.025·p95 + 0.04·r2540 + 0.015·ae30`

Constraints GE300: freqs `30/148/735/3637/18000`, Q display `0.3`, global `+3 dB`, gains `−16…+16` step `0.5`.

## CLI

```bash
python modules/unified/code/cli.py audit
python modules/unified/code/cli.py summarize
python modules/unified/code/cli.py provenance
python modules/unified/code/cli.py evaluate
python modules/unified/code/cli.py plan

# Orquestador: Azul → Mooer
python modules/unified/code/cli.py fit-azul
python modules/unified/code/cli.py fit-azul --timbre-only

# Orquestador: Azul ∘ RC → Mooer
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose minus
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose plus
python modules/unified/code/cli.py fit-azul-rc --rc-setup hybrid --compose plus
```

Opciones comunes: `--variant central|robust|safe|parametric|total`, `--timbre-only`, `--de-seeds`, `--random-starts`, `--seed`.

## Salidas

| Archivo | Contenido |
|---|---|
| `data/unified_summary.json` | Resumen cruzado |
| `data/unified_artifact_audit.csv` | Inventario de artefactos |
| `data/pipeline_edges.csv` | Provenance producer→consumer |
| `data/mooer_evaluation.csv` | RMSE regional de presets recomendados |
| `data/fits/*_mooer_preset.json` | Preset GE300 optimizado |
| `data/fits/*_target_vs_mooer.csv` | Curva target vs respuesta Mooer |
| `data/fits/*_metrics.json` | Score anti-error + RMSE regional |

## Flujo conceptual

```text
audio/cafe_vs_azul ─► emulate_azul ─► curva Café→Azul + gain
audio/rc_response  ─► rc_pedals     ─► curvas RC
rc_pedals curvas   ─► mooer_eq      ─► presets GE300 (vs RC)
Azul (± RC)        ─► unified.fit_* ─► preset Mooer anti-error
todo lo anterior   ─► unified       ─► auditoría / resumen
```
