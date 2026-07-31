# Fases 1 y 2 — Gain, nivel y estabilidad de la curva

**Fecha:** 2026-07-31 (UTC)
**Corrida base:** `det_A` (determinista, bit-idéntica a `det_B`)
**Etapa nueva:** `modules/emulate_azul/code/improve_v11.py`
**Artefactos:** `*_V11.csv` / `*_V11.json` junto a los de V10.2, que quedan intactos

Todas las cifras de abajo son medidas, no estimadas. El pipeline es determinista desde la
Fase 0, así que cualquier diferencia distinta de cero es del método, no de la ejecución.

---

## 1. El hallazgo central: la distribución del gain tiene dos poblaciones

`y − Q(f)` sobre fundamentales usables (SNR ≥ 10 dB, `match_cost` ≤ 2.8, fases `body`/`sustain`):

| Conjunto | n | mediana | media | skew | sd |
|---|---|---|---|---|---|
| Todo | 1694 | −11.84 dB | −12.84 dB | **−2.98** | 8.65 dB |
| Sin la cola | 1614 | −11.57 dB | **−11.43 dB** | **+0.26** | 5.04 dB |
| Cola (`< −25 dB`) | 80 (4.7 %) | −37.10 dB | −41.34 dB | — | — |

Con la cola dentro, los tres estimadores discrepan hasta **2.6 dB**:

```text
intercepto de mínimos cuadrados (IRLS)   -10.24 dB   <- la IRLS baja el peso de la cola
mediana                                  -11.84 dB
media                                    -12.84 dB
nivel activo medido directamente         -12.17 dB
```

Sin la cola, el skew cae a +0.26 y **todos coinciden en −11.4 … −11.6 dB**.

### La cola no es ruido

Fue la primera hipótesis y es falsa:

| Filtro | n | mediana | skew |
|---|---|---|---|
| SNR ≥ 10 dB | 1694 | −11.81 | −2.97 |
| SNR ≥ 25 dB | 1660 | −11.71 | −2.78 |
| SNR ≥ 40 dB | 1189 | −11.14 | −1.93 |

La cola **sobrevive a un filtro de SNR ≥ 40 dB**. Su SNR mediano es 28.2 dB y su `match_cost`
mediano (1.52) es **mejor** que el del resto (1.69).

### Qué es entonces

Está concentrada: **91 % viene de 3 de las 14 parejas**.

| Pareja | observaciones en la cola |
|---|---|
| `C_chromatic` | 40 |
| `B_open` | 25 |
| `A_open` | 8 |
| `G_open` | 4 |
| `E_open` | 3 |

Reparto por fase: 42 en `sustain`, 38 en `body`.

Lectura: en la cromática hay 100 notas cada 0.3 s, así que la ventana de `sustain` de una nota
contiene el ataque de la siguiente; y `B_open`/`A_open` son las fundamentales más bajas
(30.87 y 55 Hz), donde el Azul pierde fundamental. Son **casos donde la fundamental del Azul
colapsa**, no errores de emparejamiento.

**Decisión:** se tratan como sub-población documentada (`collapsed` en los artefactos), no se
silencian por peso como hacía la IRLS.

---

## 2. Cierre del bucle gain / curva (P0-4)

V10.2 ajustaba `Q(f)` con un intercepto libre de **−10.24 dB** y después **sustituía** el gain
robusto de −10.84 dB sin re-ajustar nada (`finalize_v10_2_corrected.py:51-52`). Eso dejaba
**0.60 dB de nivel atrapado dentro de la curva de timbre**.

V11 convierte el gain en offset conocido de las fundamentales, elimina la columna del intercepto
y re-ajusta `Q(f)` y los offsets, iterando hasta que el gain deja de moverse.

### Convergencia

| Iteración | gain entra | gain sale | Δ |
|---|---|---|---|
| 1 | −10.8434 | −11.0539 | −0.2105 |
| 2 | −11.0539 | −11.0621 | **−0.0081** |

Converge en **2 iteraciones**. Gain final **−11.06 dB**.

### ¿Mejoró o empeoró? (medido sobre las mismas 23 595 observaciones)

| Variante | MAE | RMSE | sesgo | MAE fund. | **sesgo fund.** |
|---|---|---|---|---|---|
| V10.2 intercepto libre | 3.8982 | 5.4560 | 0.9746 | 2.6777 | **0.1232** |
| V10.2 publicado (sustituido) | 3.9034 | 5.4746 | 1.2154 | 2.6905 | **0.7221** |
| **V11 bucle cerrado** | 3.9086 | **5.4699** | 1.1047 | **2.6878** | **0.4001** |

Lo que mejora, y es lo que importa:

- **El sesgo sistemático en fundamentales baja 45 %**: 0.7221 → 0.4001 dB.
- RMSE mejora marginalmente (−0.005 dB) y el MAE empeora marginalmente (+0.005 dB): ruido.

Trade-off honesto: el intercepto libre tiene menos sesgo aún (0.12 dB) pero su gain de −10.24 dB
no coincide con ninguna medición externa; su valor bajo sale de que la IRLS descarta la cola.

### El primer intento falló y por qué

Iterar con la **mediana** en lugar de la media del bulk divergía hacia −12.37 dB y **empeoraba**
el ajuste (sesgo fund. 0.85 dB, peor que el publicado). Con una distribución de skew −2.98, la
mediana y el intercepto ponderado no estiman lo mismo, así que el punto fijo satisfacía la
condición de la mediana pero no la de mínimos cuadrados. Se descartó.

### Efecto sobre la forma de la curva

| Región | RMSE V11−V10.2 | máx \|Δ\| |
|---|---|---|
| 20–60 Hz | 0.012 dB | 0.028 |
| 60–250 Hz | 0.036 dB | 0.066 |
| 250 Hz–1 kHz | 0.039 dB | 0.056 |
| 1–2 kHz | 0.055 dB | 0.063 |
| 2–4 kHz | 0.044 dB | 0.064 |
| 4–8 kHz | 0.003 dB | 0.011 |

La forma **no cambia** (≤ 0.055 dB). Correcto: el arreglo era de contabilidad de nivel, no de
timbre. El pico incierto de 2–4 kHz sigue pendiente de la Fase 3.

---

## 3. Estructura del gain (P0-1b)

Un escalar no describe este instrumento.

### Por cuerda

| Cuerda | gain (dB) | MAD | n | Nota al aire |
|---|---|---|---|---|
| **B** | **−15.76** | 5.00 | 292 | 30.87 Hz |
| E | −13.69 | 3.60 | 254 | 41.20 Hz |
| A | −11.66 | 4.30 | 292 | 55.00 Hz |
| G | −10.60 | 3.06 | 274 | 98.00 Hz |
| C | −10.23 | 4.30 | 502 | 130.81 Hz |
| **D** | **−8.83** | 4.30 | 80 | 73.42 Hz |

Dispersión: **6.93 dB**.

### Por registro — monótono

| Registro | gain (dB) | n |
|---|---|---|
| sub (< 60 Hz) | **−13.36** | 554 |
| low (60–150 Hz) | −12.49 | 696 |
| mid (150–400 Hz) | −9.77 | 318 |
| high (> 400 Hz) | **−9.21** | 126 |

**El Azul pierde salida progresivamente hacia los graves**, ~4.2 dB entre el registro agudo y el
subgrave. Eso es un rasgo físico del instrumento (altura de pastillas, nuez de bronce), no ruido,
y una EQ estática con un solo gain no puede representarlo.

`D` rompe la monotonía por cuerda, pero tiene sólo 80 observaciones (la pareja `D_12` aportó 6):
es la estimación menos fiable de la tabla.

---

## 4. Máscara de validez (P0-5)

`MASCARA_VALIDEZ_V11.csv` publica `valid`, `reason` y `confidence` por frecuencia.

**Sólo el 67 % de la curva publicada es una medición.** El 33 % restante es:

| Razón | Zona |
|---|---|
| `regularized_below_shrink` | < 28 Hz |
| `single_pair_inference` / `no_support` | soporte < 2 parejas |
| `regularized_above_shrink` | > 12 kHz |
| `codec_limited_aac` | > 15 kHz (AAC ~100 kbps) |

Fracción válida por región: 20–60 Hz **7.4 %**, 60–250 Hz 95.5 %, 250 Hz–2 kHz **100 %**,
4–8 kHz 32.6 %, 8–20 kHz 20.8 %.

Consecuencia directa: la banda de 18 kHz de la MOOER cae íntegra en zona no medible, así que
fijarla en −16 dB por criterio operativo es defendible; lo que **no** es defendible es tratar el
0 dB de la curva ahí como una medición.

---

## 5. Corrección: no hay tomas degradadas (P0-3 cerrado)

La auditoría inicial reportó `C_open` y `G_open` con SNR ≈ 6 dB. **Era un artefacto** de mi
estimador de piso (percentil 5 de tramos de 50 ms, contaminado por cola de notas).

Midiendo el piso sobre el silencio real previo al primer ataque:

```text
tomas con SNR < 20 dB:  0 de 32
```

Las 32 tomas son utilizables. `CALIDAD_TOMAS_V11.csv` registra piso, señal y SNR por archivo.

---

## 6. Validación cruzada por familia (P2-4)

V10.2 sólo dejaba fuera una pareja. Ahora también una familia completa:

| Familia excluida | n obs | parejas | MAE | RMSE | p95 |
|---|---|---|---|---|---|
| `open` | 9888 | 6 | 4.43 | **5.78** | 11.60 |
| `chromatic` | 4096 | 1 | 4.52 | 5.99 | 12.85 |
| `high` | 953 | 1 | 4.70 | 6.05 | 14.48 |
| `fret12` | 8658 | 6 | 4.88 | **6.56** | 14.32 |

Ninguna familia generaliza catastróficamente peor: el rango de RMSE es 5.78–6.56 dB. La curva no
depende de un solo tipo de ejercicio.

El nivel absoluto (RMSE ~6 dB sobre observaciones individuales) refleja la dispersión
evento a evento, no el error de la curva agregada.

---

## 7. Recomendación de gain

| Concepto | Valor | Uso |
|---|---|---|
| `gain_modelo_LS` | −10.24 dB | intercepto libre; sub-estima porque la IRLS descarta la cola |
| `gain_publicado_V10_2` | −10.84 dB | valor histórico, sustituido sin re-ajuste |
| **`gain_bucle_cerrado_V11`** | **−11.06 dB** | coherente con la curva: nivel fuera del timbre |
| `gain_bulk_mediana` | −11.57 dB | robusto sobre la población simétrica |
| `gain_bulk_media` | −11.43 dB | equivalente a la mediana (skew +0.26) |
| `gain_broadband_medido` | −12.17 dB | RMS activo directo, incluye la cola de colapso |

**Para uso operativo: −11.06 dB**, que es el único coherente con la curva V11 publicada.
Si se busca igualar loudness percibido de programa completo, el valor sube en magnitud hacia
−12.2 dB porque la energía media sí incluye las notas donde el Azul colapsa.

El headroom no cambia respecto de V10.2 (0.2 dB de diferencia).

---

## 8. Artefactos nuevos

```text
CURVAS_DENSAS_V11.csv                curva + valid + reason + confidence
MASCARA_VALIDEZ_V11.csv              máscara de validez por frecuencia
CONVERGENCIA_GAIN_CURVA_V11.csv      historial del bucle
GAIN_POR_PAREJA_V11.csv              gain del bulk por pareja
GAIN_ESTRUCTURA_V11.csv              gain por cuerda / registro / familia
GAIN_ESTIMADORES_V11.json            todos los estimadores con y sin la cola
CALIDAD_AJUSTE_V10_2_VS_V11.csv      MAE / RMSE / sesgo comparados
CALIDAD_TOMAS_V11.csv                piso, señal y SNR por archivo
VALIDACION_LOFO_V11.csv              leave-one-family-out
VALIDACION_LOSO_V11.csv              leave-one-string-out
COMPARACION_V10_2_VS_V11.csv         diferencia de curva por región
RESUMEN_V11.json                     resumen de la corrida
```

---

## 9. Qué queda pendiente

| Ítem | Fase |
|---|---|
| Resolver el pico de 2–4 kHz (±1.9 dB de incertidumbre) | 3 |
| Ventanas por ciclos en vez de milisegundos | 3 |
| Entrada suave de armónicos de cuerda al aire > 300 Hz | 3 |
| Curva de ataque publicada (hoy se calcula y se descarta) | 3 |
| Validación auditiva | 4 |
| Rastrear la procedencia de `gain_eff = 0.75 × display` de la MOOER | 6 |
| Regenerar los presets Azul+RC con la curva estabilizada | 6 |

**No regenerar los presets todavía:** siguen apoyados en el pico incierto de 2–4 kHz.
