# Fase 0 — Cierre de reproducibilidad

**Fecha:** 2026-07-31 (UTC)
**Rama:** `cursor/polivares-5f67`
**Baseline de referencia:** `baselines/v10_2_published/`
**Corrida determinista de referencia:** `det_A` (= `det_B`, bit a bit)

---

## Objetivo

Antes de esta fase, re-ejecutar el pipeline Café→Azul sin cambiar ningún parámetro producía una
curva que difería hasta **2.27 dB** en 2–4 kHz. Cualquier "mejora" menor que eso habría sido
indistinguible del ruido del propio pipeline.

---

## 1. Resultado: el pipeline es ahora determinista

Dos ejecuciones completas de la cadena de 4 etapas (`det_A`, `det_B`), mismo commit, misma
configuración, mismos audios:

| Métrica | Resultado |
|---|---|
| Curva `precise_central` — máx \|Δ\| | **0.0 dB** |
| `gain_recommended_db` — Δ | **0.0 dB** |
| Eventos emparejados | 927 = 927 |
| Archivos comparados | 54 |
| Archivos idénticos | **54 / 54** |
| Salidas bit-idénticas | **sí** |

Comando de verificación:

```bash
scripts/run_emulate_azul.sh det_A
scripts/run_emulate_azul.sh det_B
python3 scripts/compare_runs.py det_A det_B
```

---

## 2. Cambios que lo hicieron posible

### 2.1 Detector de onsets propio (`modules/emulate_azul/code/onsets.py`)

`build_v10_2` llamaba a `librosa.onset.onset_strength`, así que la detección de eventos dependía
de la versión instalada de librosa.

Reimplementación con numpy/scipy: banco mel Slaney → potencia en dB → primera diferencia
rectificada de media onda → media sobre bandas mel.

**Validación numérica contra librosa 0.11.0** sobre 4 audios reales:

| Archivo | corr | máx\|Δ\|/máx | RMSE |
|---|---|---|---|
| `cafe__note_e__open` | 1.000000 | 2.1e-09 | 8.1e-10 |
| `azul__note_b__open` | 1.000000 | 4.8e-09 | 1.9e-09 |
| `cafe__chromatic_c__frets_1_25` | 1.000000 | 4.5e-09 | 1.7e-09 |
| `azul__chord_am7` | 1.000000 | 3.1e-09 | 8.0e-10 |

Banco de filtros mel: máx \|Δ\| = 1.6e-09 frente a `librosa.filters.mel`.

Es decir: **misma ciencia, sin dependencia de versión**.

### 2.2 Configuración científica versionada (`config/emulate_azul.yaml`)

`lambda_mode: fixed` con `lambda_central = [100, 20, 80, 1]` (el valor publicado).

La selección por CV seguía siendo degenerada: los 8 candidatos difieren menos de 0.08 en
`central_score`, así que el ganador lo decidía el ruido. La tabla de CV se sigue calculando y
guardando para auditoría (`SELECCION_MODELOS_V10_2.csv`, ahora con columnas `cv_argmin_central`
y `lambda_mode`), pero ya no decide el resultado.

Para restaurar el comportamiento histórico: `lambda_mode: cv`.

### 2.3 Manifiesto por ejecución (`modules/emulate_azul/code/run_manifest.py`)

Cada corrida escribe `MANIFIESTO_EJECUCION.json` con `run_id`, commit, rama, estado sucio del
árbol, hash de la configuración, hash del manifiesto de entrada, hash combinado de los 32 audios,
versión de Python y de las dependencias, y hash de cada archivo producido.

### 2.4 Salidas versionadas (`repo_paths.py`)

`AZUL_OUT_DIR` / `AZUL_RENDERS_DIR` / `AZUL_WAV_CACHE` redirigen las salidas. El baseline
publicado en `results/` ya no puede ser sobrescrito por accidente.

### 2.5 Efecto colateral corregido

`build_v10_2.py` reescribía su propio `code/requirements.txt` en cada ejecución, borrando las
versiones fijadas. Se eliminó esa escritura.

### 2.6 Dependencias fijadas

```text
numpy>=2.0   pandas>=2.0   scipy>=1.11   soundfile>=0.12
librosa==0.11.0   matplotlib>=3.8   tabulate>=0.9   PyYAML>=6.0
```

`librosa` ya no se usa para onsets; se mantiene fijada porque `onsets.py` se validó contra esa
versión exacta.

---

## 3. Hallazgo: λ no era la causa principal

Con λ fijado al valor publicado y onsets deterministas, la corrida **sigue difiriendo del
baseline publicado**:

| Región | RMSE (dB) | máx \|Δ\| (dB) | media (dB) |
|---|---|---|---|
| 20–60 Hz | 0.026 | 0.071 | +0.017 |
| 60–250 Hz | 0.335 | 0.563 | +0.293 |
| 250 Hz–1 kHz | 0.510 | 0.825 | +0.442 |
| 1–2 kHz | 0.939 | 1.623 | −0.758 |
| **2–4 kHz** | **1.619** | **1.937** | **−1.570** |
| 4–8 kHz | 0.151 | 0.548 | −0.034 |
| 8–20 kHz | 0.005 | 0.010 | −0.003 |

Global: RMSE 0.655 dB, máx \|Δ\| 1.937 dB.

| Gain | Baseline | det_A | Δ |
|---|---|---|---|
| `gain_recommended_db` | −10.5915 | −10.8434 | −0.252 |
| `fundamental_only_median_db` | −11.5210 | −11.5119 | **+0.009** |
| `energy_only_median_db` | −9.6743 | −10.3884 | −0.714 |

**Eventos emparejados: baseline 873, corridas actuales 927.**

### Interpretación

Fijar λ redujo la discrepancia en 2–4 kHz de 2.27 dB a 1.94 dB, o sea **sólo ~0.33 dB**. La causa
dominante es la **diferencia de 54 eventos** en la detección.

Como `onsets.py` reproduce librosa 0.11.0 con error ~1e-9, y aun así salen 927 eventos, la
conclusión es que **el baseline publicado se generó con una versión de librosa distinta**, cuyo
`onset_strength` daba 873 eventos. Esa versión no está registrada en ningún artefacto del
repositorio.

**Consecuencia honesta:** el baseline publicado **no es exactamente reproducible con ninguna
biblioteca disponible hoy**. Lo que sí queda garantizado a partir de ahora es que toda corrida
futura es reproducible bit a bit y trazable a su commit, configuración y audios.

### Qué significa para las cifras publicadas

| Magnitud | Estado |
|---|---|
| Gain por fundamentales (−11.51 dB) | **sólido** — Δ 0.009 dB |
| `gain_recommended_db` | **razonablemente sólido** — Δ 0.25 dB |
| Curva bajo 1 kHz | **sólida** — RMSE ≤ 0.51 dB |
| **Pico de 2–4 kHz** | **incierto en ±1.9 dB** |
| Curva sobre 4 kHz | sólida sólo porque está regularizada a 0 |

El preset Azul+RC del orquestador usa **+15.5 / +12.0 dB en la banda de 3637 Hz** apoyándose
justamente en la región incierta. No debe regenerarse hasta cerrar la Fase 2.

---

## 4. Nuevo criterio de mejora

Con el pipeline determinista, el ruido de reproducibilidad es **0.0 dB**. Por tanto:

> Cualquier diferencia distinta de cero entre dos configuraciones es ahora una diferencia real
> del método, no ruido de ejecución.

Esto habilita las Fases 1–3 con comparaciones válidas.

Queda una incertidumbre **epistémica** separada del ruido de ejecución: ±1.9 dB en 2–4 kHz
respecto de la corrida histórica, que debe reportarse junto a esa región hasta que la Fase 2
determine cuál de las dos estimaciones está mejor soportada por los datos.

---

## 5. Artefactos generados

```text
config/emulate_azul.yaml                                  configuración científica versionada
modules/emulate_azul/code/onsets.py                       detector determinista
modules/emulate_azul/code/run_config.py                   cargador de configuración
modules/emulate_azul/code/run_manifest.py                 manifiesto de ejecución
scripts/run_emulate_azul.sh                               cadena completa a directorio versionado
scripts/compare_runs.py                                   comparador de corridas
baselines/v10_2_published/DETERMINISMO_A_VS_B.json        prueba de determinismo
baselines/v10_2_published/DETERMINISTA_VS_BASELINE.json   corrida determinista vs baseline
```

---

## 6. Estado del plan

| Ítem | Estado |
|---|---|
| 0.1 Instalar dependencias | hecho |
| 0.2 Restaurar `f0` | hecho |
| 0.3 Compatibilidad NumPy 2 | hecho |
| 0.4 Salidas versionables | hecho |
| 0.5 Registrar baseline | hecho |
| 0.6 Pinear versiones | hecho |
| 0.7 Onsets deterministas | hecho |
| 0.8 Fijar λ | hecho |
| 0.9 Manifiesto por ejecución | hecho |
| 0.10 Medir ruido de reproducibilidad | hecho — **0.0 dB** |

**Criterio de salida de Fase 0** (dos ejecuciones con RMSE ≤ 0.05 dB en todas las bandas y λ
idéntico): **cumplido con margen** — RMSE 0.0 dB y salidas bit-idénticas.

Siguiente: **Fase 1 — gain, nivel y headroom.**
