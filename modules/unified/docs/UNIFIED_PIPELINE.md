# Pipeline unificado

## Etapas ligeras (recomendadas primero)

```bash
python modules/unified/code/cli.py audit
python modules/unified/code/cli.py summarize
python modules/unified/code/cli.py evaluate
python modules/unified/code/cli.py plan
```

## Orquestador AUDIO: cualquier bajo → Azul ± RC → Mooer

Aplica curvas **al archivo que le pases ahora** (FIR on-demand). No reutiliza renders históricos.

```bash
# Emular Azul desde cualquier bajo seco
python modules/unified/code/cli.py process -i /ruta/bajo.wav --chain azul

# Cascada Azul + RC
python modules/unified/code/cli.py process -i /ruta/bajo.m4a --chain azul+rc --rc-setup bass

# Un solo GE300 (preset anti-error)
python modules/unified/code/cli.py process -i /ruta/bajo.wav --chain mooer --mooer-preset azul

# Near-realtime (OLA por bloques)
python modules/unified/code/cli.py process -i /ruta/bajo.wav --chain azul --streaming

# Fidelidad vs toma real
python modules/unified/code/cli.py verify -i cafe.m4a -r azul.m4a --chain azul
```

Audio out: `modules/unified/_runs/process/` (gitignored).  
Chequeo: `*_measured_transfer.csv` — RMSE FIR vs curva pretendida debe ser ≈ 0 dB.

## Orquestador PRESETS: Azul (± RC) → Mooer anti-error

```bash
python modules/unified/code/cli.py fit-azul
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose plus
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose minus --timbre-only
```

Salidas en `modules/unified/data/fits/`.

## Informe PDF orquestado (raíz del repo)

```bash
python modules/unified/code/cli.py informe
```

Contenido:

1. Curvas Café→Azul (V10.2) + gain
2. Curvas RC Bajo / Híbrido / Guitarra
3. Mezcla **Azul(+gain)+RC** = target compuesto
4. 3 presets Mooer que emulan esa mezcla (Q=0.3, freqs locked, **18000=−16**, global=+3)

Fórmula: `target = azul_central + gain_azul + rc_setup`

Salida: `INFORME_ORQUESTADOR_AZUL_RC_MOOER.pdf` + `modules/unified/data/ORCHESTRATED_PRESETS_AZUL_PLUS_RC_LOCKED18K.json`

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
