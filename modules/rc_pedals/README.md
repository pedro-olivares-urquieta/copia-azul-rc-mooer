# Módulo: rc_pedals

Objetivo: reconstruir las respuestas de los pedales/RC en modos **bass**, **hybrid** y **guitar** desde ruido rosa y barridos.

## Entradas de audio

- [`../../audio/rc_response`](../../audio/rc_response)
- Inventario: [`../../manifests/rc_response_inventory.csv`](../../manifests/rc_response_inventory.csv)

Señales:

- `pink__off` / `pink__rc_{bass,hybrid,guitar}`
- `sweep_1_22k__off` / `sweep_1_22k__rc_{bass,hybrid,guitar}`

## Contenido

| Ruta | Qué es |
|---|---|
| `code/source_reconstruction_pipeline.py` | DSP de reconstrucción (pink + chirps) |
| `code/01_audio_reconstruction_and_384_audit.py` | Auditoría 192 vs 384 PPO |
| `data/` | Curvas refinadas, QC, sweeps, validación de método |
| `config/config.json` | Parámetros de análisis |
| `checksums/` | SHA-256 de audios originales de la corrida |
| `docs/` | Pipeline DSP, calidad de audios, reproducibilidad |

## Salida hacia otros módulos

Las curvas RC reconstruidas alimentan [`../mooer_eq`](../mooer_eq) para buscar presets del GE300.

## API / CLI (sin DSP pesado)

```bash
python modules/rc_pedals/code/rc_cli.py audit
python modules/rc_pedals/code/rc_cli.py summarize
```

Código reutilizable: `rc_artifacts.py` (`load_refined_curves`, `summarize_curves`, `audit_artifacts`).

## Paths

Vía `code/repo_paths.py`:

- Audio canónico: `audio/rc_response` (nombres normalizados)
- Nombres lógicos legacy (`Pink.m4a`, etc.) mapeados a esos archivos
- Datos: `data/`
- Cache WAV: `_cache/wav/`

```bash
python modules/rc_pedals/code/01_audio_reconstruction_and_384_audit.py
python modules/rc_pedals/code/source_reconstruction_pipeline.py \
  --output-dir modules/rc_pedals/_runs/reconstruction
```
