# Reproducibilidad y trazabilidad

## Orden de ejecución

```bash
python -m pip install -r code/requirements.txt
python code/01_audio_reconstruction_and_384_audit.py
python code/02_multizone_discrete_optimization.py
python code/03_constraint_diagnostics.py
python code/04_operational_selection.py
python code/05_comparison_by_region.py
```

## Entradas

Los ocho M4A se incluyen en `audio/originales/`.

## Semillas

Las semillas y parámetros están en `config/analysis_config.json`.

## Trazabilidad

`checksums/SHA256SUMS.txt` y `checksums/file_manifest_sha256.csv` contienen hashes de todos los archivos.

## Honestidad del óptimo

Los presets son las mejores soluciones encontradas y verificadas localmente bajo la búsqueda documentada. No se demuestra un óptimo global de las 1.160 millones de combinaciones.
