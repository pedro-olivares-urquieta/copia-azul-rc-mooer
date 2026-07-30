# Módulo: emulate_azul

Objetivo: estimar y aplicar la transferencia **Café → Azul** para emular el Bajo Azul.

## Entradas de audio

- Pares musicales: [`../../audio/cafe_vs_azul`](../../audio/cafe_vs_azul)
- Inventario: [`../../manifests/cafe_vs_azul_pairs.csv`](../../manifests/cafe_vs_azul_pairs.csv)

## Contenido

| Ruta | Qué es |
|---|---|
| `code/` | Pipeline V10.2 (`build_v10_2.py` + reparaciones + finalize + postprocess) |
| `docs/PROMPT_MAESTRO_V10_2.md` | Especificación científica completa |
| `results/` | Curvas, métricas, informes, PNGs de la corrida V10.2 |

## Pipeline legacy (orden)

```bash
python code/build_v10_2.py
python code/repair_v10_2_gain.py
python code/extract_tonal_repair.py
python code/finalize_v10_2_corrected.py
python code/postprocess_v10_2.py
```

## Resultado clave V10.2

- Gain global ≈ **-10.6 dB**
- Curva: poco cambio <60 Hz; recorte ~80–630 Hz; boost ~1–3 kHz
- Preset paramétrico en `results/PRESET_PARAMETRICO_V10_2.csv`

## API / CLI (sin DSP pesado)

```bash
python modules/emulate_azul/code/azul_cli.py audit
python modules/emulate_azul/code/azul_cli.py summarize
```

Código reutilizable: `azul_artifacts.py` (`load_curve`, `summarize_curve`, `audit_artifacts`).

## Paths

Vía `code/repo_paths.py`:

- Audio: `audio/cafe_vs_azul`
- Resultados: `results/`
- Cache WAV: `_cache/wav/`
- Renders: `renders/`
- Exports zip: `exports/`
- Curvas V9/V10.1 opcionales: `legacy_curves/`

```bash
python modules/emulate_azul/code/build_v10_2.py
```

Dependencias: `code/requirements.txt` (+ `ffmpeg`).
