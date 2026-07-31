# Auditoría inicial del repositorio `copia-azul-rc-mooer`

**Fecha:** 2026-07-30 (UTC)
**Rama auditada:** `cursor/polivares-5f67`
**Commit base:** `6bb5e39`
**Alcance:** inventario completo, mapa de dependencias, ejecución de comandos de sólo lectura,
QC de audio fuente y reproducción del pipeline Café→Azul vigente.

Esta auditoría **no modifica resultados científicos**. Los únicos cambios de código realizados en
esta fase son correcciones de reproducibilidad (P0/P1) documentadas en §7, sin las cuales el
pipeline no arranca en el entorno actual.

---

## 1. Arquitectura real encontrada

```text
copia-azul-rc-mooer/
├── audio/
│   ├── cafe_vs_azul/        32 archivos .m4a (16 pares Café/Azul)
│   └── rc_response/          8 archivos .m4a (pink + sweep, OFF y 3 setups RC)
├── manifests/
│   ├── cafe_vs_azul_pairs.csv    pair_id, kind, label, position, rutas, sha256
│   ├── rc_response_inventory.csv
│   ├── NAMING.md
│   └── rename_map.csv
├── modules/
│   ├── emulate_azul/   code · results (58 artefactos) · docs · legacy_curves · renders · exports
│   ├── rc_pedals/      code · data · config · checksums · docs
│   ├── mooer_eq/       code · data · config · plots · docs
│   └── unified/        code · data · docs
├── scripts/            reorganize_repo.py
├── baselines/          (creado en esta auditoría)
└── INFORME_ORQUESTADOR_AZUL_RC_MOOER.pdf
```

**Observación arquitectónica:** los cuatro módulos existen y respetan mayormente el
desacoplamiento pedido. `mooer_eq` no depende de Café/Azul. `unified` importa las APIs de los
otros módulos vía `bridge.py` (carga dinámica con purga de `sys.modules`), lo que funciona pero es
frágil: no hay paquetes instalables ni `__init__.py`, y `python -m modules.X` **no está disponible**
(los CLIs se invocan por ruta de archivo).

**No existe:** `config/` centralizado, `tests/`, `reports/`, `archive/`.
No hay ningún test automatizado en el repositorio (`0` archivos `test_*.py`).

---

## 2. Flujo real de datos

```text
audio/cafe_vs_azul ──┐
manifests/pairs.csv ─┴─► emulate_azul/code/build_v10_2.py
                            │  (librosa onsets · DP matching · multitaper · WLS+IRLS)
                            ├─► results/MATCHING_EVENTOS_V10_2.csv
                            ├─► results/TRAYECTORIAS_*.csv
                            └─► results/CURVAS_DENSAS_V10_2.csv (provisional)
                                   │
      repair_v10_2_gain.py ────────┤ FUNDAMENTALES_CORREGIDAS_V10_2.csv
      extract_tonal_repair.py ─────┤ TONAL_HARMONICS_CORRECTED_V10_2.csv
      finalize_v10_2_corrected.py ─┴─► CURVAS_DENSAS_V10_2.csv  (FINAL)
                                       GAIN_GLOBAL_V10_2.csv    (-10.59 dB)
                                       renders/
      postprocess_v10_2.py ───────────► PNG + métricas

audio/rc_response ──► rc_pedals/code/source_reconstruction_pipeline.py
                        └─► data/refined_curves_192ppo.csv
                                │
                                ├─► mooer_eq (optimización vs RC)
                                └─► unified/targets.py
                                        │
emulate_azul curva + gain ──────────────┴─► unified: fit / process / informe
```

**Punto crítico de trazabilidad:** la curva y el gain publicados **no** salen de una sola
ejecución de `build_v10_2.py`, sino de una cadena de 4 scripts donde `finalize_v10_2_corrected.py`
recalcula el gain y reescribe `CURVAS_DENSAS_V10_2.csv`. No existe un `run_id` ni manifiesto que
registre esa cadena.

---

## 3. Pipeline Café→Azul vigente (cómo se obtuvo la curva actual)

### 3.1 Cadena de cómputo

| Paso | Archivo | Qué produce |
|---|---|---|
| 1 | `build_v10_2.py` | eventos, matching, observaciones, ajuste inicial, renders |
| 2 | `repair_v10_2_gain.py` | fundamentales con SNR recalculado |
| 3 | `extract_tonal_repair.py` | armónicos tonales con SNR recalculado |
| 4 | `finalize_v10_2_corrected.py` | **curva final + gain final −10.59 dB** |
| 5 | `postprocess_v10_2.py` | gráficos y métricas |

### 3.2 Modelo estadístico

Diseño lineal único (`build_v10_2.py:346-358`) con:

- intercepto global `G` (sólo activo en observaciones de tipo `fundamental`)
- offsets por cuerda (6), registro (4) y fase (5), con penalización de suma cero
- spline `Q(f)` de **86 nodos** (16 en 20–120 Hz, 40 medios, 30 agudos)
- penalizaciones: segunda diferencia (suavidad), *shrink* a 0 fuerte bajo 28 Hz y sobre 12 kHz,
  ancla de media en 30–2500 Hz
- ajuste por **WLS + IRLS** (5 iteraciones, pesos tipo Huber)
- λ elegido por CV dejando **una pareja** fuera (8 candidatos × 16 folds)
- CI por **bootstrap de parejas** (120–140 remuestreos)

Observaciones (`build_v10_2.py:270-331`):

| Tipo | Fórmula | Entra al ajuste final |
|---|---|---|
| `fundamental` | `dB(A_azul) − dB(A_cafe)` por proyección sinusoidal | Sí |
| `tonal_harmonic` | ratio relativo a la fundamental (invariante a `G`) | Sí |
| `band_residual` | banda − fundamental de cuerpo | Sí (peso ×0.35) |
| `attack multiscale` | 6 ventanas × 6 bandas | **No — sólo gráficos** |

### 3.3 Gain global (−10.59 dB)

`finalize_v10_2_corrected.py:17-38` calcula, **por pareja**:

- `gain_fundamental_db` = mediana de `(y − Q(f))` sobre fundamentales con `SNR ≥ 10` y fases `body`/`sustain`
- `gain_energy_db` = `20·log10(RMS_azul / RMS_cafe_ecualizado)` aplicando la EQ **con gain 0**
- `gain_combined_db = 0.65 · fundamental + 0.35 · energy`
- peso `= √n / MAD`
- valor publicado = **mediana ponderada entre parejas**, CI por bootstrap (2000)

Luego (`:51-52`) el intercepto del modelo se **sustituye** por ese valor:
`bc[IG] = gain`, **sin re-ajustar `Q(f)` ni los offsets**.

### 3.4 Ventanas temporales

Fijas en segundos, no en ciclos (`build_v10_2.py:220-223`):

| Periodo | attack | body | sustain | decay |
|---|---|---|---|---|
| 0.6 s | 0–75 ms | 155–320 ms | 320–490 ms | 440–560 ms |
| 0.3 s | 0–45 ms | 90–175 ms | 175–255 ms | 225–285 ms |

Consecuencia medida: a 31 Hz el `body` cubre ≈ **5 ciclos**; a 1 kHz ≈ **165 ciclos**.

### 3.5 Reglas de graves y agudos

- **< 28 Hz y > 12 kHz:** penalización de encogimiento ×40 → la curva tiende a 0 dB por
  regularización, **no por medición** (`build_v10_2.py:379-385`)
- **cuerdas al aire:** contenido **> 300 Hz excluido** como medición directa
  (`:295-298`, `:325-326`; `CONFIG_V10_2.json: open_above_300_weight = 0`)
- **corte de soporte agudos:** ≈ 8000 Hz para la ablación `no_high` (`:519-520`)
- gates de SNR: 8 dB (armónicos build), 10 dB (armónicos corregidos y gain), 14 dB (band residual)

---

## 4. QC de audio fuente (ejecutado)

### 4.1 Integridad e ingesta

| Métrica | Resultado |
|---|---|
| Archivos | 40 (32 Café/Azul + 8 RC) |
| Códec | AAC, **todos** |
| Sample rate | 44100 Hz, **todos** |
| Canales declarados | 2 |
| **Canales reales** | **dual-mono: L idéntico a R en 32/32** (`rms(L−R) = 0`) |
| Bitrate | ~98–108 kbps |
| SHA-256 vs manifiesto | **32/32 coinciden** |
| Clipping (\|x\|>0.999) | 0 muestras en todos |
| DC offset | ≈ +2.3e-5 constante en todos (artefacto de codificación, despreciable) |

**Implicación:** los archivos son AAC ~100 kbps. A ese bitrate el codificador suele recortar o
alterar el contenido por encima de ~15–16 kHz. Cualquier lectura de la curva por encima de esa
zona debe considerarse **no medible**, no "plana".

### 4.2 Niveles por instrumento

| Instrumento | peak medio | RMS medio | crest medio |
|---|---|---|---|
| Café | **−18.19 dBFS** | **−32.68 dBFS** | 14.49 dB |
| Azul | **−30.14 dBFS** | **−44.92 dBFS** | 14.78 dB |

### 4.3 Diferencia de nivel por pareja (Azul − Café)

Medido sobre RMS de tramos activos (umbral = 4× piso de ruido):

| Pareja | Δ activo (dB) | `gain_energy_db` pipeline | Δ − pipeline |
|---|---|---|---|
| A_open | −12.11 | −10.22 | −1.89 |
| B_open | −16.23 | −15.45 | −0.78 |
| C_open | −12.12 | −10.59 | −1.53 |
| D_open | −12.62 | −9.30 | −3.32 |
| E_open | −14.85 | −12.93 | −1.92 |
| G_open | −8.09 | −9.03 | +0.94 |
| A_12 | −12.60 | −9.76 | −2.84 |
| B_12 | −14.59 | −12.99 | −1.60 |
| C_12 | −9.60 | −4.32 | −5.28 |
| D_12 | −12.07 | −8.35 | −3.72 |
| E_12 | −14.47 | −12.32 | −2.15 |
| G_12 | −11.16 | −9.56 | −1.60 |
| C_24 | −9.22 | −7.09 | −2.13 |
| Am7 | −10.00 | −9.59 | −0.41 |
| Cmaj7 | −10.57 | −8.14 | −2.43 |
| C_chromatic | −12.21 | −10.54 | −1.67 |

**Mediana Δ activo = −12.11 dB** (σ = 2.24; rango −16.23 … −8.09)
**Correlación Δ activo vs `gain_energy_db` = 0.842**

### 4.4 Pisos de ruido y SNR

| Pareja | piso Café | piso Azul | SNR Café | SNR Azul |
|---|---|---|---|---|
| C_open | **−39.7 dBFS** | −69.9 | **6.4 dB** | 24.5 |
| G_open | **−39.0 dBFS** | −53.0 | **6.4 dB** | 12.4 |
| A_open | −57.0 | −70.2 | 24.0 | 25.1 |
| B_12 | −77.0 | −77.8 | 49.7 | 35.9 |
| C_24 | −78.8 | −80.7 | 49.3 | 42.0 |
| Cmaj7 | −75.4 | −76.6 | 56.2 | 46.9 |

**Dos tomas de Café (`C_open`, `G_open`) tienen SNR ≈ 6 dB.** Son las peores del conjunto y
justamente `G_open` es el outlier de nivel (−8.09 dB frente a la mediana −12.11).

---

## 5. Reproducción del baseline

### 5.1 Estado antes de la auditoría

El pipeline **no era ejecutable** en el entorno:

1. `librosa` no instalado (requerido en `build_v10_2.py:86,189`) → `ModuleNotFoundError`
2. `audio_utils_v7.load_pairs()` no aportaba la clave `f0`, requerida por
   `build_v10_2.py:208` (`detect_mono(yc, p['f0'])`) → `KeyError: 'f0'`
3. `np.trapz` fue eliminado en NumPy 2 (instalado: 2.x) y se usa en
   `build_v10_2.py:127,255,319` → `AttributeError`
4. `repo_paths.OUT` apuntaba fijo a `results/`: **ejecutar el pipeline habría sobrescrito el
   baseline publicado**

### 5.2 Registro del baseline

Antes de ejecutar nada se creó:

```text
baselines/v10_2_published/BASELINE_MANIFEST.json     58 archivos con sha256 + bytes
baselines/v10_2_published/BASELINE_KEY_NUMBERS.json  cifras ancla
```

Cifras ancla del baseline:

```text
gain_recommended_db            -10.5915
gain_ci95                      [-11.8015, -8.3581]
gain_fundamental_only_db       -11.5210
gain_energy_only_db             -9.6743
model_intercept_diagnostic_db   -9.9366
curva: 4096 puntos, min -2.734 dB, max +4.120 dB
central @   30 Hz   +0.005 dB
central @   55 Hz   -0.291 dB
central @  100 Hz   -1.422 dB
central @  500 Hz   -1.683 dB
central @ 1800 Hz   +4.083 dB   (máximo)
central @ 8000 Hz   -0.006 dB
central @15000 Hz   -0.000 dB
```

### 5.3 Resultado de la reproducción (cadena completa de 4 scripts)

Ejecutado: `build_v10_2.py` → `repair_v10_2_gain.py` → `extract_tonal_repair.py` →
`finalize_v10_2_corrected.py`, con salida a `modules/emulate_azul/_runs/<run_id>/results`.
Entorno: numpy 2.x, librosa 0.11.0. Exit code 0.

**Gain global — REPRODUCIBLE**

| Métrica | Baseline | Reproducción | Δ |
|---|---|---|---|
| `gain_recommended_db` | −10.5915 | **−10.7471** | **−0.156** |
| `fundamental_only_median_db` | −11.5210 | −11.4834 | +0.038 |
| `energy_only_median_db` | −9.6743 | −10.2177 | −0.544 |
| `model_intercept_diagnostic_db` | −9.9366 | −10.1876 | −0.251 |

Gain por pareja: mediana `|Δ|` = **0.43 dB**, ninguna pareja se desvía más de 0.87 dB.

**Curva de timbre — REPRODUCIBLE SALVO 2–4 kHz**

Global: RMSE = **0.666 dB**, máx `|Δ|` = **2.272 dB**, p95 `|Δ|` = 1.903 dB, mediana ≈ 0.

| Región | RMSE (dB) | máx \|Δ\| (dB) | Veredicto |
|---|---|---|---|
| 20–60 Hz | 0.013 | 0.035 | Reproducible *(trivial: está regularizada a 0)* |
| 60–250 Hz | 0.190 | 0.353 | Reproducible |
| 250 Hz–1 kHz | 0.549 | 0.775 | Aceptable |
| 1–2 kHz | 0.630 | 1.474 | Marginal |
| **2–4 kHz** | **1.823** | **2.272** | **NO reproducible** |
| 4–8 kHz | 0.133 | 0.513 | Reproducible |
| 8–20 kHz | 0.002 | 0.004 | Reproducible *(trivial: regularizada a 0)* |

Puntos clave:

```text
   Hz     baseline    repro     delta
 1400      +3.522    +3.228    -0.293
 1800      +4.083    +3.061    -1.022     <- el "pico" publicado
 2500      +3.396    +1.146    -2.250     <- discrepancia máxima
 3000      +2.605    +0.532    -2.073
```

**Causas identificadas de la no reproducibilidad:**

1. **λ elegido por CV es inestable.** El baseline (`CONFIG_V10_2.json`) seleccionó
   `(100, 20, 80, 1)` — candidato 3 de 8. La reproducción seleccionó `(20, 5, 20, 0.7)` —
   candidato 1. Los `central_score` de los 8 candidatos están dentro de ~0.08 entre sí
   (`SELECCION_MODELOS_V10_2.csv`), así que el ganador depende del ruido.
2. **La detección de eventos no es determinista entre versiones de librosa.**
   Eventos emparejados: baseline **873**, reproducción **927** (+6.2 %).
   Coste mediano de matching: 1.5804 → 1.6928.
3. **El conteo de observaciones cambia por pareja.** `A_12`: `n_fund` 32 → 100.

**Conclusión de reproducibilidad:** el nivel global es una cifra sólida; la **magnitud del boost
de medios-altos (2–4 kHz) no lo es**. La curva publicada afirma +3.4 dB a 2.5 kHz donde una
re-ejecución del mismo código da +1.1 dB.

### 5.4 Gain por pareja del baseline (dispersión)

| Pareja | `gain_combined_db` |
|---|---|
| C_12 | **−5.40** |
| C_24 | −7.45 |
| Cmaj7 | −8.14 |
| D_open | −8.36 |
| D_12 | −8.47 |
| G_open | −9.01 |
| Am7 | −9.59 |
| G_12 | −10.20 |
| A_12 | −10.80 |
| A_open | −11.17 |
| C_chromatic | −11.31 |
| C_open | −11.73 |
| E_open | −12.69 |
| E_12 | −13.42 |
| B_12 | −13.97 |
| B_open | **−16.65** |

**Dispersión = 11.25 dB** entre la pareja más alta y la más baja.

---

## 6. Hallazgos

### P0-1 — [CORREGIDO 2026-07-31] El gain es del instrumento, no de la sesión

```text
ESTADO: cerrado. La hipótesis inicial de no identificabilidad era incorrecta.

Evidencia decisiva:
  1. El operador confirma que ambos instrumentos se grabaron en las MISMAS
     condiciones (misma cadena, misma ganancia de entrada).
  2. El test del piso de ruido que se había usado para sospechar de la sesión
     NO ES VÁLIDO en este material. Si el piso fuera ruido de cadena sería
     constante entre tomas de una misma sesión; medido sobre el silencio previo
     al primer ataque (>= 2 s en 15/16 parejas):
        piso Café: -78.2 ... -54.0 dBFS  -> rango 24.2 dB
        piso Azul: -83.8 ... -71.1 dBFS  -> rango 12.8 dB
     Un rango de 24 dB dentro de la misma sesión demuestra que el piso está
     dominado por ruido del propio instrumento (pastillas, zumbido, cuerdas) y
     por el códec AAC, que escalan con el nivel del programa.
  3. Por eso d_floor (-11.07 dB) sigue a d_signal (-12.17 dB) y el SNR se
     conserva (d_snr -2.00 dB): un instrumento de menor salida entrega también
     menos zumbido de pastilla a través de la misma cadena. Esa firma es
     compatible tanto con "otra ganancia de sesión" como con "instrumento más
     débil", así que el test no discrimina.

Conclusión:
  La diferencia de nivel Azul-Café es una propiedad del INSTRUMENTO.
     mediana de nivel activo   -12.17 dB
     gain del pipeline         -10.59 dB (baseline) / -10.84 dB (determinista)
  La diferencia entre ambos (~1.5 dB) es esperable y correcta: el gain del
  pipeline se mide DESPUÉS de compensar el timbre (la ruta de energía aplica la
  EQ con gain 0 y luego compara RMS), así que parte de los -12.17 dB la absorbe
  la curva.

Lo que SIGUE siendo un problema (ver P0-1b):
  la dispersión de 11.25 dB entre parejas.
```

### P0-1b — Dispersión de 11.25 dB en el gain entre parejas

```text
Hallazgo:
  El gain por pareja va de -5.40 dB (C_12) a -16.65 dB (B_open).

Evidencia (gain_combined_db, GAIN_POR_PAREJA_Y_FUENTE_V10_2.csv):
     C_12    -5.40      G_12   -10.20      E_12   -13.42
     C_24    -7.45      A_12   -10.80      B_12   -13.97
     Cmaj7   -8.14      A_open -11.17      B_open -16.65
     D_open  -8.36      C_chrom-11.31
     D_12    -8.47      C_open -11.73
     G_open  -9.01      E_open -12.69
     Am7     -9.59
  Rango: 11.25 dB. Mediana ponderada publicada: -10.59 dB.
  Nivel activo bruto por pareja: rango -16.23 ... -8.09 dB (sigma 2.24).

Impacto:
  Un solo escalar no describe el comportamiento del instrumento: el Azul es
  ~16 dB más débil en B_open (cuerda grave al aire) y sólo ~5 dB en C_12. Esa
  estructura es información real, no ruido, y hoy se colapsa a un número.

Hipótesis:
  H1 - el desbalance de salida depende de la cuerda y del registro (pastillas,
       altura respecto a cada cuerda, nuez de bronce en el Azul)
  H2 - parte de la dispersión es error de estimación en las parejas con poco
       soporte (D_12 tiene solo 6 observaciones de fundamental)
  H3 - parte la absorbe mal la curva de timbre y reaparece como nivel

Corrección propuesta:
  1. Reportar el gain por cuerda y por registro además del escalar global.
  2. Cerrar el bucle G/Q (ver P0-4): parte de la dispersión puede ser fuga.
  3. Sensibilidad leave-one-pair-out del gain.
  4. Distinguir gain_de_medicion / gain_perceptual / gain_operativo.

Validación:
  · Recalcular el gain excluyendo las parejas con SNR bajo (P0-3)
  · Comparar la dispersión antes y después de cerrar el bucle G/Q
  · Verificar si el gain por cuerda correlaciona con los offsets de cuerda que
    el modelo ya estima (CORRELACION_EQ_OFFSETS_CUERDA.csv)

Prioridad: P0
```

### P0-2 — El boost de 2–4 kHz de la curva publicada no es reproducible

```text
Hallazgo:
  Re-ejecutar la cadena completa sin cambiar ningún parámetro científico produce
  +1.15 dB a 2.5 kHz donde el baseline publica +3.40 dB (delta -2.25 dB).

Evidencia:
  baselines/v10_2_published/REPRODUCCION_VS_BASELINE_POR_REGION.csv
    2k-4k: rmse 1.823 dB, max_abs 2.272 dB, mean -1.755 dB
  Resto del espectro: RMSE <= 0.63 dB
  CONFIG_V10_2.json selected_central = [100,20,80,1]
  Reproduccion selecciono [20,5,20,0.7]
  SELECCION_MODELOS_V10_2.csv: los 8 candidatos difieren <0.08 en central_score
  Eventos emparejados: 873 (baseline) vs 927 (reproduccion)

Impacto:
  El rasgo mas llamativo de la curva Cafe->Azul (el pico de medios-altos) es
  inestable. Ese pico se propaga al preset Azul+RC del orquestador (+15.5 dB en la
  banda de 3637 Hz de la MOOER en los tres presets), es decir, una decision de
  hardware apoyada en un valor no reproducible.

Hipotesis:
  H1 - la seleccion de lambda por CV es degenerada: los 8 candidatos son casi
       equivalentes y el ganador lo decide el ruido de la particion
  H2 - la deteccion de onsets depende de la version de librosa, cambiando el conjunto
       de eventos y por tanto las observaciones de 2-4 kHz
  H3 - la zona 2-4 kHz se apoya en pocas parejas con soporte independiente

Correccion propuesta:
  1. Fijar lambda explicitamente en configuracion versionada, o promediar el modelo
     sobre los candidatos dentro del margen de ruido (model averaging).
  2. Reemplazar/duplicar la deteccion de onsets con un detector propio y determinista
     (flux espectral por bandas), sin dependencia de version.
  3. Reportar el pico de 2-4 kHz con su intervalo de reproducibilidad, no como valor puntual.
  4. Repetir la cadena con N semillas y publicar la envolvente.

Validacion:
  · Ejecutar la cadena 5 veces con seeds distintos y medir la dispersion en 2-4 kHz
  · Leave-one-family-out especifico sobre esa banda
  · Verificar si el preset MOOER cambia al usar la curva reproducida

Prioridad: P0
```

### P0-3 — Dos tomas de Café tienen SNR ≈ 6 dB y contaminan el análisis

```text
Hallazgo:
  cafe__note_c__open y cafe__note_g__open tienen pisos de ruido de -39.7 y -39.0 dBFS,
  con SNR activo de 6.4 dB en ambos casos.

Evidencia:
  · Tabla §4.4; el resto del conjunto está entre 24 y 56 dB de SNR
  · G_open es el outlier de nivel: Δ activo -8.09 dB frente a mediana -12.11
  · el pipeline sólo filtra por SNR a nivel de observación (8/10/14 dB), no marca
    archivos completos como degradados

Impacto:
  El ruido inflacta el RMS del Café en esas dos parejas, sesgando el gain hacia
  valores menos negativos, y puede inyectar energía espuria en la curva.

Hipótesis:
  Zumbido de red o ruido ambiental en esas dos tomas específicas.

Corrección propuesta:
  · QC de archivo con umbral de SNR y bandera `degraded`
  · Análisis espectral del piso para identificar 50/60 Hz y armónicos
  · Ponderar o excluir esas parejas y reportar el efecto

Validación:
  Recalcular curva y gain con y sin esas parejas; comparar en validación cruzada.

Prioridad: P0
```

### P0-4 — Desacople incompleto entre `G` y `Q(f)`

```text
Hallazgo:
  Q(f) se ajusta conjuntamente con un intercepto G = -9.94 dB, pero el valor publicado
  G = -10.59 dB se sustituye después sin re-ajustar Q ni los offsets.

Evidencia:
  finalize_v10_2_corrected.py:45-52
    bc,dfc,_ = m.fit_model(obs, lc, 'JOINT')     # G interno = -9.9366
    ...
    bc[m.IG] = gain                              # G := -10.5915
  GAIN_GLOBAL_V10_2.csv: model_intercept_diagnostic_db = -9.9366

Impacto:
  Queda ~0.65 dB de fuga G/Q dentro de `precise_central_db`. La curva de timbre
  publicada contiene una fracción de nivel que debería estar en el gain.

Hipótesis:
  Se priorizó un estimador de gain más robusto sin cerrar el bucle del ajuste.

Corrección propuesta:
  Iterar: fijar G robusto -> re-ajustar Q y offsets con G como offset conocido ->
  recalcular G -> repetir hasta convergencia (2-3 iteraciones deberían bastar).

Validación:
  Verificar que el intercepto re-ajustado converge al gain robusto y comparar la
  curva antes/después; medir el cambio en validación cruzada.

Prioridad: P0
```

### P0-5 — Regiones no medidas se publican como 0 dB

```text
Hallazgo:
  Bajo 28 Hz y sobre 12 kHz la curva vale ~0 dB por regularización, no por medición.

Evidencia:
  build_v10_2.py:379-385  ->  if f<28 or f>12000: s = 40*shrink
  CURVAS_DENSAS_V10_2.csv @ 20 Hz: effective_pairs = 0, support_state = "No identificado",
                                    precise_central_db = 0.0014
  Audio: AAC ~100 kbps limita el contenido fiable por encima de ~15-16 kHz (§4.1)

Impacto:
  Un consumidor que lea la curva sin la columna `support_state` interpretará
  "0 dB medido" donde en realidad no hay dato. El fitter de la MOOER puede intentar
  seguir esas regiones.

Corrección propuesta:
  · Publicar máscara `valid` explícita y propagarla a `unified` y `mooer_eq`
  · Que el optimizador MOOER pese por confianza y no persiga regiones inválidas
  · Documentar el límite del códec

Validación:
  Comprobar que los presets no cambian al enmascarar >15 kHz; si cambian, el ajuste
  estaba siendo guiado por datos inexistentes.

Prioridad: P0
```

### P1-1 — El pipeline no era ejecutable (3 fallos de entorno)

```text
Hallazgo:
  librosa ausente, `f0` ausente en el cargador de pares, y `np.trapz` eliminado en NumPy 2.

Evidencia:
  · ModuleNotFoundError: librosa (requirements.txt lo lista; no estaba instalado)
  · KeyError: 'f0' en build_v10_2.py:208 (audio_utils_v7 no lo proveía)
  · AttributeError: np.trapz en build_v10_2.py:127

Impacto:
  Reproducibilidad nula: era imposible verificar ninguna cifra publicada.

Corrección aplicada en esta fase:
  · pip install librosa (0.11.0)
  · audio_utils_v7.expected_f0(): afinación B0/E1/A1/D2/G2/C3 y trastes 12/24.
    Verificado contra TRAYECTORIAS_FUNDAMENTALES_V10_2.csv (p.ej. B_open 30.87 vs 30.89 medido)
  · shim `np.trapz = np.trapezoid` (misma regla trapezoidal)

Validación:
  Ejecución del pipeline en curso hacia directorio versionado (§5).

Prioridad: P1 (bloqueante)
```

### P1-2 — El pipeline sobrescribía el baseline

```text
Hallazgo:
  repo_paths.OUT apuntaba fijo a modules/emulate_azul/results/.

Evidencia:
  repo_paths.py (versión anterior): OUT = MODULE / "results"
  build_v10_2.py escribe ~58 artefactos en OUT.

Impacto:
  Cualquier re-ejecución destruía el baseline publicado sin posibilidad de comparación.

Corrección aplicada:
  OUT/AUD/WAV overridables por AZUL_OUT_DIR / AZUL_RENDERS_DIR / AZUL_WAV_CACHE.
  BASELINE_OUT expuesto para lectura del baseline.

Prioridad: P1
```

### P1-3 — Sin `run_id`, sin manifiesto de ejecución, sin versionado semántico

```text
Hallazgo:
  Ningún artefacto registra commit, hash de config, hash de inputs, seed ni dependencias.

Evidencia:
  CONFIG_V10_2.json contiene la seed y lambdas, pero no commit ni hashes de entrada.
  No existe MANIFIESTO_*.json de ejecución.
  Nombres como CURVAS_DENSAS_V10_2.csv se reescriben en sitio por finalize_*.

Impacto:
  No se puede saber qué código produjo qué número.

Corrección propuesta:
  Manifiesto por ejecución (run_id, commit, config_hash, input_hash, seed, deps, outputs).

Prioridad: P1
```

### P1-4 — Cero tests

```text
Hallazgo:
  No hay ningún test en el repositorio.

Evidencia:
  Búsqueda de test_*.py / tests/ -> 0 resultados.

Impacto:
  Los bugs P1-1 (tres fallos de import/API) habrían sido detectados por un smoke test.

Corrección propuesta:
  Tests unitarios de dB<->amplitud, interpolación log, composición de curvas,
  cuantización MOOER, límites, headroom; smoke test de cada CLI.

Prioridad: P1
```

### P2-1 — Datos de ataque calculados y descartados

```text
Hallazgo:
  El análisis multiescala de ataque (6 ventanas x 6 bandas) se computa y guarda, pero
  no entra al ajuste de la curva.

Evidencia:
  build_v10_2.py:312-320 genera las observaciones; el diseño (:346-358) no las usa.
  ATAQUES_MULTIESCALA_V10_2.csv existe sólo para gráficos.

Impacto:
  Coste de cómputo sin retorno, y la diferencia transitoria entre instrumentos queda
  fuera del modelo (una EQ estática no puede capturarla, pero sí podría informar el
  peso de las regiones agudas).

Prioridad: P2
```

### P2-2 — Ventanas en segundos, no en ciclos

```text
Hallazgo:
  Las fases se definen en milisegundos fijos; los graves reciben pocos ciclos.

Evidencia:
  build_v10_2.py:220-223 (75/155/320/490 ms). A 31 Hz el `body` cubre ~5 ciclos.

Impacto:
  Resolución y varianza muy desiguales entre 30 Hz y 1 kHz. Contribuye a la
  inestabilidad de subgraves.

Prioridad: P2
```

### P2-3 — Exclusión dura de cuerdas al aire sobre 300 Hz

```text
Hallazgo:
  Regla binaria: el contenido >300 Hz de cuerdas al aire se descarta por completo.

Evidencia:
  build_v10_2.py:295-298, :325-326; CONFIG_V10_2.json open_above_300_weight = 0

Impacto:
  Correcto para no confundir armónicos con la fundamental, pero elimina información
  útil de brillo/nuez que podría entrar con peso reducido en la curva de armónicos.

Prioridad: P2
```

### P2-4 — Validación cruzada sólo por pareja

```text
Hallazgo:
  La CV deja fuera una pareja. No hay leave-one-family-out, -string-out ni -register-out.

Evidencia:
  build_v10_2.py:421-437 (lambda CV), :682-688 (identificabilidad). Ninguna agrupa por familia.

Impacto:
  No se sabe si la curva generaliza a un tipo de ejercicio no visto (p.ej. sólo acordes).

Prioridad: P2
```

### P2-5 — Parejas con soporte muy débil

```text
Hallazgo:
  D_12 aportó 6 observaciones de fundamental; D_open 62; frente a >150 en otras.

Evidencia:
  GAIN_POR_PAREJA_Y_FUENTE_V10_2.csv (n_fund: D_12 = 6)

Impacto:
  Alta varianza; el peso √n/MAD lo mitiga parcialmente pero no lo elimina.

Prioridad: P2
```

### P3-1 — Coste de cómputo

```text
Hallazgo:
  El pipeline decodifica 32 m4a y hace ~120 bootstrap de ajuste completo.
  El motor MOOER exhaustivo tardaba >17 min por preset antes de la optimización
  con rejilla de 1 dB + refinamiento (ahora ~12 s).

Prioridad: P3
```

### P4-1 — CLIs no uniformes

```text
Hallazgo:
  No existe `python -m modules.X`. Cada módulo se invoca por ruta de archivo y con
  subcomandos distintos. Falta --config, --run-id, --dry-run, --log-level.

Prioridad: P4
```

### P4-2 — Estilo de código de una línea

```text
Hallazgo:
  build_v10_2.py concentra lógica científica en líneas de 200-2000 caracteres
  (p.ej. :629 genera un informe completo en una sola línea).

Impacto:
  Auditabilidad muy baja; imposible hacer diffs útiles.

Prioridad: P4
```

---

## 7. Cambios realizados en esta fase (sólo desbloqueo, sin tocar la ciencia)

| Archivo | Cambio | Motivo |
|---|---|---|
| `modules/emulate_azul/code/audio_utils_v7.py` | `expected_f0()` + claves `f0`, `label`, `position` | P1-1: el pipeline no arrancaba |
| `modules/emulate_azul/code/build_v10_2.py` | shim `np.trapz = np.trapezoid` | P1-1: NumPy 2 |
| `modules/emulate_azul/code/repo_paths.py` | `OUT`/`AUD`/`WAV` overridables + `BASELINE_OUT` | P1-2: protección del baseline |
| `baselines/v10_2_published/` | manifiesto de 58 hashes + cifras ancla | registrar baseline |
| entorno | `pip install librosa` | P1-1 |

Ningún parámetro científico (λ, seeds, pesos, umbrales, reglas de 300 Hz o 28 Hz) fue modificado.

---

## 8. Comandos ejecutados

```bash
# inventario y git
git status -sb && git log --oneline -5
ls -la audio/cafe_vs_azul audio/rc_response

# QC de ingesta
ffprobe -v error -print_format json -show_format -show_streams <cada archivo>

# QC de niveles / pisos de ruido / SHA-256  (script Python ad hoc)
#   -> /tmp/qc_cafe_azul.csv, /tmp/pair_deltas.csv, /tmp/pair_deltas_merged.csv

# dependencias
python3 -c "import librosa"        # ANTES: ModuleNotFoundError
pip install librosa                # 0.11.0

# reproducción del baseline (directorio versionado, NO sobre results/)
AZUL_OUT_DIR=modules/emulate_azul/_runs/<run_id>/results \
AZUL_RENDERS_DIR=modules/emulate_azul/_runs/<run_id>/renders \
python3 modules/emulate_azul/code/build_v10_2.py
```

**Tests existentes ejecutados:** ninguno — el repositorio no contiene tests (P1-4).

---

## 9. Resumen de riesgos

| Área | Riesgo | Severidad |
|---|---|---|
| Gain | ~~No identificable frente a la ganancia de sesión~~ **descartado 2026-07-31: es del instrumento** | — |
| Gain | 11.25 dB de dispersión entre parejas | **Alta** |
| Curva | Pico 2–4 kHz incierto en ±1.9 dB | **Alta** |
| Graves | <28 Hz publicado como 0 dB sin medición | Alta |
| Agudos | >15 kHz limitado por AAC ~100 kbps | Alta |
| Datos | 2 tomas de Café con SNR ≈ 6 dB | Alta |
| Modelo | Fuga G/Q de ~0.65 dB | Media |
| Reproducibilidad | Sin run_id ni manifiesto | Media |
| Software | Cero tests | Media |
| Validación | Sólo CV por pareja | Media |

---

## 10. Archivos creados

```text
AUDITORIA_INICIAL_REPOSITORIO.md
PLAN_DE_MEJORA_PRIORIZADO.md
baselines/v10_2_published/BASELINE_MANIFEST.json
baselines/v10_2_published/BASELINE_KEY_NUMBERS.json
modules/emulate_azul/_runs/<run_id>/     (reproducción, no versionada en git)
```
