# Módulo: unified

Orquestador de los tres módulos del proyecto:

1. `emulate_azul` — transferencia Café→Azul  
2. `rc_pedals` — respuestas RC (bass/hybrid/guitar)  
3. `mooer_eq` — modelo EQ Mooer GE300 + presets  

## Idea clave

**No es un historial de renders.** Las curvas medidas se aplican **on-demand** a **cualquier audio de bajo** (wav/m4a/flac/…). Cada `process` carga el archivo, construye FIR y escribe salida + chequeo de fidelidad.

## Cadenas de audio

| `--chain` | Qué aplica al audio | Uso |
|---|---|---|
| `azul` | FIR Café→Azul (curva + gain) | Emular Azul desde cualquier bajo seco |
| `azul+rc` | Azul FIR → RC FIR | Cascada física Azul+boost |
| `mooer` | FIR del preset GE300 | Un solo pedal aproxima Azul / Azul+RC |
| `rc+mooer` | RC FIR → Mooer residual | RC físico ON + residual GE300 |

Aliases de preset Mooer: `azul`, `azul_timbre`, `azul+rc`, `azul-rc`.

## CLI — procesar audio real

```bash
# Cualquier bajo → emulación Azul (fidelidad FIR típica ~0.01 dB vs curva)
python modules/unified/code/cli.py process -i /ruta/a/tu_bajo.wav --chain azul

# Cascada Azul + RC bass
python modules/unified/code/cli.py process -i tu_bajo.m4a --chain azul+rc --rc-setup bass

# Solo Mooer (preset anti-error que aproxima Azul+RC)
python modules/unified/code/cli.py process -i tu_bajo.wav --chain mooer --mooer-preset azul+rc

# Path block/OLA (near-realtime); default = offline fftconvolve
python modules/unified/code/cli.py process -i tu_bajo.wav --chain azul --streaming

# Verificar contra una toma real de referencia
python modules/unified/code/cli.py verify \
  -i audio/cafe_vs_azul/cafe__note_e__open.m4a \
  -r audio/cafe_vs_azul/azul__note_e__open.m4a \
  --chain azul
```

Salidas de audio en `modules/unified/_runs/process/` (gitignored).  
Cada process escribe `*_measured_transfer.csv` (curva medida Welch vs pretendida).

## Informe PDF (Azul+gain mezclado con RC → 1 preset Mooer)

Cada preset **no** es RC aparte ni Azul aparte: es la **mezcla**

`target = Azul(central) + gain_Azul + RC(setup)`

y el GE300 la emula en un solo EQ, con:

- Q display = **0.3**
- Frecs locked: **30 / 148 / 735 / 3637 / 18000**
- Banda **18000 Hz = −16 dB** (lock)
- Global **+3 dB**

```bash
python modules/unified/code/cli.py informe
# → INFORME_ORQUESTADOR_AZUL_RC_MOOER.pdf
```

JSON: `modules/unified/data/ORCHESTRATED_PRESETS_AZUL_PLUS_RC_LOCKED18K.json`

Motor de búsqueda (`mooer_fit.py`, `quality=high|max`):

- Exhaustivo discreto en bandas libres (con 18 kHz locked → óptimo global)
- Semillas LSQ + DE + dual annealing + LHS (modo heurístico si 5 bandas libres)
- ILS + pairwise + triple polish
- Objetivo anti-error: `worst + 0.35·avg + 0.10·global + …`

## CLI — fit presets (curvas → GE300)

```bash
python modules/unified/code/cli.py fit-azul
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose plus
python modules/unified/code/cli.py fit-azul-rc --rc-setup bass --compose minus --timbre-only
```

## Auditoría

```bash
python modules/unified/code/cli.py audit
python modules/unified/code/cli.py summarize
python modules/unified/code/cli.py evaluate
python modules/unified/code/cli.py plan
```

## Fidelidad

1. **DSP correcto**: `fidelity_vs_intended_curve.rmse_db ≈ 0` → el FIR aplicó la curva al audio de verdad.  
2. **Match al instrumento**: `verify` compara transfer dry→procesado vs dry→toma real. Una EQ estática no elimina offsets por cuerda / ataque / no-linealidades (eso ya lo documenta V10.2).

## Flujo

```text
cualquier bajo.wav/m4a
        │
        ▼
 unified process --chain …
        │  FIR on-demand (Azul ± RC ± Mooer)
        ▼
 out.wav + measured_transfer.csv
```
