# copia-azul-rc-mooer

Repositorio modular para:

1. Emular el Bajo Azul desde el Café  
2. Reconstruir respuestas de pedales RC  
3. Modelar/optimizar el EQ del Mooer GE300 en PC  
4. Orquestar Azul (± RC) → EQ Mooer GE300 anti-error  

## Módulos

| Módulo | Rol | CLI rápida |
|---|---|---|
| [`modules/emulate_azul`](modules/emulate_azul) | Transferencia Café→Azul (V10.2) | `python modules/emulate_azul/code/azul_cli.py summarize` |
| [`modules/rc_pedals`](modules/rc_pedals) | Curvas RC bass/hybrid/guitar | `python modules/rc_pedals/code/rc_cli.py summarize` |
| [`modules/mooer_eq`](modules/mooer_eq) | Modelo EQ GE300 + presets | `python modules/mooer_eq/code/mooer_cli.py evaluate` |
| [`modules/unified`](modules/unified) | Orquestador Azul±RC→Mooer | `python modules/unified/code/cli.py fit-azul` |

## Audio normalizado

| Carpeta | Contenido |
|---|---|
| [`audio/cafe_vs_azul`](audio/cafe_vs_azul) | 16 pares Café/Azul |
| [`audio/rc_response`](audio/rc_response) | Pink + sweep OFF/RC |

Convención: [`manifests/NAMING.md`](manifests/NAMING.md)

## Relación

```text
audio/cafe_vs_azul ──► emulate_azul ──► curva Café→Azul
audio/rc_response  ──► rc_pedals    ──► curvas RC
rc_pedals curvas   ──► mooer_eq     ──► presets GE300 (vs RC)
Azul (± RC)        ──► unified      ──► fit Mooer anti-error
todo               ──► unified      ──► audit / summary
```

## Empezar por unified

```bash
python modules/unified/code/cli.py audit
python modules/unified/code/cli.py summarize
python modules/unified/code/cli.py evaluate
python modules/unified/code/cli.py plan

# AUDIO REAL (cualquier bajo, on-demand — no renders históricos)
python modules/unified/code/cli.py process -i audio/cafe_vs_azul/cafe__note_e__open.m4a --chain azul
python modules/unified/code/cli.py process -i /ruta/tu_bajo.wav --chain mooer --mooer-preset azul+rc
python modules/unified/code/cli.py process -i /ruta/tu_bajo.wav --chain azul+rc --rc-setup bass

# Fit presets GE300 (anti-error)
python modules/unified/code/cli.py fit-azul
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose plus
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose minus --timbre-only

# Informe PDF ordenado (Azul + RC + 3 presets, 18k=-16)
python modules/unified/code/cli.py informe
# → INFORME_ORQUESTADOR_AZUL_RC_MOOER.pdf
```

## Pipelines heavy (DSP completo)

```bash
python modules/emulate_azul/code/build_v10_2.py
python modules/rc_pedals/code/source_reconstruction_pipeline.py
python modules/mooer_eq/code/02_multizone_discrete_optimization.py
python modules/mooer_eq/code/04_operational_selection.py
python modules/mooer_eq/code/05_comparison_by_region.py
```

Requisitos: `ffmpeg` + deps en cada `code/requirements.txt`.
