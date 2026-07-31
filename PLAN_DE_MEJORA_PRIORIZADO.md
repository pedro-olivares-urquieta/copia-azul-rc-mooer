# Plan de mejora priorizado — `copia-azul-rc-mooer`

**Fecha:** 2026-07-30 (UTC)
**Basado en:** [`AUDITORIA_INICIAL_REPOSITORIO.md`](AUDITORIA_INICIAL_REPOSITORIO.md)
**Baseline protegido en:** `baselines/v10_2_published/`

Este plan es **ejecutable en orden**. Cada elemento indica qué se cambia, cómo se valida y qué
criterio decide si se acepta o se descarta. Ninguna mejora se da por buena sin comparación
reproducible contra el baseline.

---

## Regla de aceptación transversal

Una mejora se acepta sólo si cumple **todas**:

1. No degrada el error de **validación** (no de entrenamiento) más allá de la incertidumbre
   declarada de la región afectada.
2. Es **determinista**: dos ejecuciones con la misma seed dan el mismo resultado.
3. El baseline sigue disponible y comparable.
4. El cambio queda registrado con `run_id`, commit y hashes.
5. Si empeora algo, se documenta el trade-off explícitamente.

Una mejora se **descarta** si sólo mejora RMSE de entrenamiento, o si su ganancia cae dentro del
ruido de reproducibilidad medido (§ Fase 0).

---

## Fase 0 — Cerrar la reproducibilidad (bloqueante) · P0/P1

Sin esto, ninguna comparación posterior tiene valor: hoy la propia curva publicada difiere
**2.27 dB** en 2–4 kHz al re-ejecutarse.

| # | Acción | Archivo(s) | Validación | Estado |
|---|---|---|---|---|
| 0.1 | Instalar y fijar dependencias (`librosa`, `tabulate`) con versiones | `requirements.txt` | el pipeline arranca | **hecho** (versiones aún sin pinear) |
| 0.2 | Restaurar `f0` esperado en el cargador de pares | `audio_utils_v7.py` | f0 coincide con `TRAYECTORIAS_FUNDAMENTALES` (B_open 30.87 vs 30.89 medido) | **hecho** |
| 0.3 | Compatibilidad NumPy 2 (`np.trapz`) | `build_v10_2.py` | ejecución completa sin `AttributeError` | **hecho** |
| 0.4 | Salidas versionables por entorno (no sobrescribir baseline) | `repo_paths.py` | `AZUL_OUT_DIR` respetado | **hecho** |
| 0.5 | Registrar baseline con hashes y cifras ancla | `baselines/v10_2_published/` | 58 archivos con sha256 | **hecho** |
| 0.6 | **Pinear versiones exactas** en `requirements.txt` (`librosa==0.11.0`, `numpy`, `scipy`) | `*/code/requirements.txt` | reinstalación limpia reproduce | pendiente |
| 0.7 | **Detector de onsets determinista propio** (flux espectral multibanda) que elimine la dependencia de la versión de librosa | nuevo `onsets.py` | eventos emparejados estables ±0 entre corridas y versiones | pendiente |
| 0.8 | **Fijar λ en configuración** en vez de elegirlo por CV degenerada; alternativamente *model averaging* sobre los candidatos dentro del margen de ruido | `config/emulate_azul.yaml` | dos corridas seleccionan el mismo modelo | pendiente |
| 0.9 | **Manifiesto por ejecución** (`run_id`, commit, config_hash, input_hash, seed, deps, outputs) | nuevo `run_manifest.py` | cada corrida escribe `MANIFIESTO_*.json` | pendiente |
| 0.10 | **Medir el ruido de reproducibilidad**: 5 corridas con seeds distintos → envolvente por región | `baselines/` | tabla de dispersión por banda | pendiente |

**Criterio de salida de Fase 0:** dos ejecuciones consecutivas dan RMSE de curva ≤ 0.05 dB entre
sí en **todas** las bandas, y el λ seleccionado es idéntico.

---

## Fase 1 — Gain, nivel y headroom (55 % → aquí está el problema más grave) · P0

El gain de −10.59 dB **no es separable** de la ganancia de grabación de la sesión.

| # | Acción | Método | Validación |
|---|---|---|---|
| 1.1 | **Diagnóstico de no identificabilidad** | contrastar H1 (ganancia de sesión: el piso de ruido escala con la señal) vs H2 (instrumento más débil: el piso queda constante y el SNR cae ~12 dB) usando `d_floor` y `SNR` por pareja | tabla de decisión por pareja; hoy la evidencia es mixta (piso Azul más bajo en 11/16, pero SNR cae en notas pisadas) |
| 1.2 | **Análisis espectral del piso de ruido** | Welch del piso en tramos silenciosos; buscar 50/60 Hz y armónicos | identificar zumbido en `C_open`/`G_open` (SNR ≈ 6 dB) |
| 1.3 | **Marcar archivos degradados** | QC de archivo con umbral SNR; bandera `degraded` en el manifiesto | recalcular gain sin esas parejas y reportar Δ |
| 1.4 | **Descomponer el gain en conceptos distintos** | `gain_de_medicion`, `gain_de_fundamentales`, `gain_perceptual` (loudness), `gain_de_compensacion`, `headroom_preventivo`, `gain_operativo_recomendado` | tabla `GAIN_CAFE_AZUL_ANALISIS.csv` con los 6 valores y su incertidumbre |
| 1.5 | **Estimadores adicionales** | loudness por evento, nivel de sustain vs ataque, peak, crest factor, energía de graves, true peak tras FIR | comparar los 15 estimadores del §19 del encargo |
| 1.6 | **Sensibilidad leave-one-pair-out del gain** | recalcular la mediana ponderada quitando cada pareja | rango de variación; hoy la dispersión bruta es **11.25 dB** (C_12 −5.40 … B_open −16.65) |
| 1.7 | **Auditoría de headroom** | true peak del render con FIR + gain; verificar que no se aplica el gain dos veces (`total_central_with_gain_db` **o** `apply_eq(gain)`, nunca ambos) | ningún render supera 0 dBFS true peak |
| 1.8 | **Recomendación práctica separada del valor científico** | documento con el valor a usar en la MOOER y por qué difiere del estimado | `ANALISIS_GAIN_CAFE_AZUL.md` |

**Criterio de aceptación:** el informe declara explícitamente qué parte del gain es identificable
y qué parte no, con un valor operativo justificado y un headroom que no satura.

---

## Fase 2 — Estabilizar la curva Café→Azul · P0

| # | Acción | Método | Validación |
|---|---|---|---|
| 2.1 | **Cerrar el bucle G/Q** | iterar: G robusto fijo → re-ajustar `Q(f)` y offsets con G como offset conocido → recalcular G → repetir hasta convergencia | el intercepto converge al gain robusto; hoy queda ~0.65 dB de fuga (−9.94 vs −10.59) |
| 2.2 | **Máscara de validez explícita** | columna `valid` derivada de `effective_pairs`, SNR y límite del códec (~15 kHz para AAC 100 kbps) | `mooer_eq` y `unified` dejan de perseguir regiones sin datos |
| 2.3 | **Ventanas por ciclos, no por milisegundos** | ventana = máx(N ciclos, mínimo absoluto), N dependiente de banda | comparar dispersión de subgraves antes/después; hoy 31 Hz recibe ~5 ciclos vs ~165 a 1 kHz |
| 2.4 | **Suavizado dependiente de confianza y de región** | fracción de octava variable + penalización de 2ª derivada por banda; conservar curva sin suavizar | pendiente máxima y nº de picos antes/después |
| 2.5 | **Entrada suave de armónicos de cuerda al aire >300 Hz** | peso reducido en la curva de armónicos en vez de exclusión binaria | comparar 2–8 kHz con y sin; hoy el peso es 0 |
| 2.6 | **Incorporar ataque como curva separada y ponderada** | usar `ATAQUES_MULTIESCALA` (hoy calculado y descartado) para una `CURVA_ATAQUE` publicada | validación auditiva en transitorios |
| 2.7 | **Modelo estadístico jerárquico real** | efectos aleatorios por archivo / familia / cuerda; comparar mediana ponderada vs Huber vs Tukey vs bootstrap jerárquico | validación cruzada por familia |

---

## Fase 3 — Validación cruzada y experimentos comparativos · P1/P2

| # | Acción | Notas |
|---|---|---|
| 3.1 | `leave-one-family-out` (open / fret12 / high / chromatic / chord) | hoy sólo existe leave-one-pair-out |
| 3.2 | `leave-one-string-out` (B/E/A/D/G/C) | detecta el confundido cuerda↔frecuencia en subgraves |
| 3.3 | `leave-one-register-out` | sub / low / mid / high |
| 3.4 | Evitar fuga: no repartir eventos del mismo archivo entre train y validación | la unidad estadística es el archivo, no el evento |
| 3.5 | Experimentos del §24 del encargo (Welch vs multitaper, ventana fija vs adaptativa, media vs mediana robusta, gain conjunto vs separado, curva libre vs regularizada, ponderación uniforme vs confianza) | tabla `EXPERIMENTOS_CAFE_AZUL.md` con hipótesis/método/resultado/decisión |
| 3.6 | Reportar error por región, por cuerda y por familia | `VALIDACION_CAFE_AZUL.csv` |

---

## Fase 4 — Validación auditiva · P2

| # | Acción |
|---|---|
| 4.1 | Renders `cafe_original`, `azul_real`, `cafe_baseline`, `cafe_nuevo`, `cafe_mooer_nuevo` |
| 4.2 | Dos sets: **nivel real** y **nivel igualado** (para juzgar timbre sin nivel) |
| 4.3 | Comparativas por familia: al aire, traste 12, traste 24, acordes, cromático |
| 4.4 | Residual/null test sólo donde sea técnicamente válido (no se espera cancelación entre interpretaciones humanas) |

El motor de audio on-demand ya existe (`unified process`) y aplica la curva con **RMSE ≈ 0.01 dB**
respecto de la curva pretendida, verificado por Welch. Ese bloque **no** es el problema.

---

## Fase 5 — Curvas RC · P2 (10 %)

| # | Acción |
|---|---|
| 5.1 | Auditar OFF/ON, clipping, alineación y deconvolución del sweep |
| 5.2 | No promediar pink y sweep a ciegas: fusión por coherencia/SNR con pesos justificados |
| 5.3 | Publicar `respuesta_pink`, `respuesta_sweep`, `respuesta_fusionada`, `respuesta_suavizada`, `respuesta_recomendada`, `gain_pedal`, `incertidumbre`, `mascara_validez` por setup |
| 5.4 | Mantener 192 PPO como resolución; usar 384 PPO sólo como auditoría, no como precisión física |

---

## Fase 6 — Modelo y optimizador MOOER · P1/P2 (10 %)

| # | Acción | Notas |
|---|---|---|
| 6.1 | **Rastrear el origen de `gain_eff = 0.75 × display`** | el encargo exige no usarla sin medición de respaldo y rango de validez documentado |
| 6.2 | **Corregir el rango del gain global a −60 … +3 dB** y relación 1:1 con el valor mostrado | revisar si el código asume otro mínimo |
| 6.3 | **Versionar la calibración** (`calibration_version`, archivos, método, residuos, rango válido, incertidumbre, fecha, hash) | hoy la calibración es una constante en `mooer_model.py` sin procedencia |
| 6.4 | **Ponderar el objetivo por confianza** y penalizar headroom, oscilaciones y pendientes irreproducibles | evita que una región inválida imponga un gain extremo |
| 6.5 | Mantener la demostración de óptimo discreto | ya implementado: con 18 kHz bloqueado la búsqueda es exhaustiva sobre las 4 bandas libres (rejilla 1 dB + refinamiento 0.5 dB + pulido) |
| 6.6 | Reportar `error_en_30Hz`, `error_en_fundamentales`, `headroom`, `peak_estimado`, `preset_hash` | ampliar el JSON de preset |

**Nota de coherencia:** los tres presets Azul+RC actuales usan **+15.5 / +12.0 dB en la banda de
3637 Hz**, guiados por el pico de 2–4 kHz que la Fase 0 demostró no reproducible. Esos presets
deben regenerarse **después** de estabilizar la curva.

---

## Fase 7 — `unified` e incertidumbre · P2 (5 %)

| # | Acción |
|---|---|
| 7.1 | Propagar incertidumbre Café→Azul + RC + calibración MOOER hasta el objetivo del optimizador |
| 7.2 | Verificar que el gain global no se aplica dos veces en ninguna cadena (`azul` vs `total`) |
| 7.3 | Sustituir terminología: no "emulación exacta" sino modelo / estimación / aproximación / preset optimizado |
| 7.4 | Contratos de datos con esquema validado (dataclasses o Pydantic) para curvas, presets y ejecuciones |

---

## Fase 8 — Arquitectura, tests y documentación · P1/P4 (5 %)

| # | Acción |
|---|---|
| 8.1 | `config/` centralizado: `project.yaml` + un YAML por módulo; sacar del código umbrales, pesos, regiones, seeds |
| 8.2 | Tests unitarios: dB↔amplitud, interpolación log, composición de curvas, suavizado, integración de fundamentales, diseño FIR, cuantización y límites MOOER, métricas, hashes, headroom |
| 8.3 | Tests de integración: un smoke test por CLI (habría detectado los 3 fallos de la Fase 0) |
| 8.4 | Tests de regresión sobre un dataset pequeño, distinguiendo regresión de software de regresión científica |
| 8.5 | Paquetes importables + `python -m modules.X` con `--config`, `--run-id`, `--dry-run`, `--seed`, `--log-level` |
| 8.6 | Logging estructurado en lugar de `print` |
| 8.7 | Refactor progresivo de `build_v10_2.py` (líneas de hasta ~2000 caracteres) en funciones auditables, **sin cambiar la ciencia en el mismo commit** |
| 8.8 | Documentación del §40 del encargo, empezando por `PIPELINE_EMULATE_AZUL.md` y `LIMITACIONES_CONOCIDAS.md` |

---

## Orden de ejecución recomendado

```text
1. Fase 0  (0.6 → 0.10)   cerrar reproducibilidad y medir el ruido de la propia cadena
2. Fase 1  (1.1 → 1.8)    gain / nivel / headroom  ← problema más grave
3. Fase 2  (2.1 → 2.7)    estabilizar la curva
4. Fase 3                 validación cruzada real
5. Fase 4                 validación auditiva
6. Fase 6                 MOOER (calibración con procedencia) y regenerar presets
7. Fase 5                 RC
8. Fase 7                 unified + incertidumbre
9. Fase 8                 arquitectura, tests, documentación
```

**Por qué la Fase 0 va primero:** hoy la diferencia entre dos ejecuciones del mismo código es de
2.27 dB en 2–4 kHz. Cualquier "mejora" menor que eso sería indistinguible del ruido del propio
pipeline, así que medir mejoras antes de cerrar la reproducibilidad sería autoengaño.

---

## Lo que NO se debe hacer todavía

| No hacer | Motivo |
|---|---|
| Reorganizar carpetas | la estructura modular actual es razonable y funciona |
| Reescribir `build_v10_2.py` de golpe | primero hay que poder comparar; el refactor debe ir en commits separados de los cambios científicos |
| Cambiar `mooer_model.py` (`0.75`, Q efectiva) | antes hay que rastrear la procedencia de esas constantes (6.1) |
| Regenerar los presets Azul+RC | dependen del pico de 2–4 kHz aún inestable |
| Borrar `results/`, `legacy_curves/`, informes previos o audios | son el baseline y la evidencia histórica |
| Introducir dependencias pesadas nuevas | sin justificación medida |
| Publicar una "V11" | no existe todavía ninguna mejora validada |
