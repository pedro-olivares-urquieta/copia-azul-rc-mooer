# Qué aprender del informe V4.1 y qué se adoptó

**Fecha:** 2026-07-31 (UTC)
**Nuestro pipeline:** V10.2 → V11 (cierre G/Q) → **V12 (adopciones de esta revisión)**
**Referencia externa:** informe metodológico V4.1 (912 frecuencias, PSD Hann)

Se revisó primero nuestro propio código para no "adoptar" cosas que ya teníamos.

---

## 1. El hallazgo más valioso de todos

V4.1 usa el **tamaño de muestra efectivo de Kish**:

```text
N_efectivo = (Σ pesos)² / Σ pesos²
```

Nosotros teníamos `effective_pairs`, que era simplemente **un conteo de parejas distintas**.
No distingue cuatro parejas equilibradas de cuatro donde una lleva todo el peso.

Al implementarlo de verdad:

| Métrica por frecuencia | Mediana |
|---|---|
| `pair_count` (lo que teníamos) | **3.0** |
| `effective_pairs_kish` (Kish real) | **1.26** |

**En la frecuencia típica contribuyen 3 parejas, pero el peso efectivo es de 1.26.**
Es decir: **una sola pareja domina casi por completo casi todo el espectro.**

Eso explica de golpe tres cosas que ya habíamos medido por separado:

- el pico de 2–4 kHz se mueve ±1.9 dB entre corridas;
- dos métodos independientes discrepan 1.5 dB RMSE en forma;
- `effective_score` tiene mediana **0.000**.

No es un problema de método ni de densidad de rejilla. Es que **16 parejas de grabaciones no
alcanzan para sostener el detalle fino de una curva**, y hasta ahora no lo estábamos midiendo.

---

## 2. Convergencia independiente del gain

Dos pipelines distintos, sobre los mismos 32 audios:

| Estimador | Valor |
|---|---|
| V10.2 publicado | −10.84 dB |
| V11 bucle cerrado | −11.06 dB |
| V11 bulk media | −11.43 dB |
| V11 bulk mediana | −11.57 dB |
| **V4.1 crudo sustain** | **−11.63 dB** |
| **V4.1 residual** | **−11.94 dB** |
| **V12 neutralidad energética** | **−12.04 dB** |
| Nivel activo medido directo | −12.17 dB |

Antes, nuestro gain discrepaba 1.1–1.3 dB de la medición directa. Con neutralidad energética
(§4) **la discrepancia se cierra a 0.13 dB** y coincide con V4.1 dentro de 0.1 dB.

El gain es, con esto, la magnitud más sólida del proyecto.

---

## 3. Discrepancia en presencia: hasta 6 dB

| Hz | V10.2 | V11 | **V4.1** |
|---|---|---|---|
| 515 | −1.72 | −0.85 | **+3.49** |
| 958 | +1.03 | +1.25 | +3.49 |
| 1360 | +3.36 | +2.66 | +4.08 |
| 2630 | +3.12 | +1.16 | **+6.61** |
| 4120 | +0.77 | +0.33 | **+6.34** |
| 5190 | +0.01 | +0.08 | **+4.33** |

Dos análisis independientes de los mismos audios discrepan **hasta 6 dB** en la banda de
presencia. Y es precisamente la banda donde el preset MOOER pone **+15.5 dB en 3637 Hz**.

### Mi hipótesis, puesta a prueba

Planteé que la causa era una diferencia de convención: V10.2 fija el promedio **sin ponderar**
de `Q(f)` a cero entre 30 y 2500 Hz (`build_v10_2.py:391`, peso 300), mientras V4.1 impone
**neutralidad energética ponderada por el espectro del Café**. Como la energía de un bajo está
en los graves, un realce ancho de +5 dB en 0.5–5 kHz casi no cuesta energía total, así que la
convención de V4.1 lo permite y la nuestra lo prohíbe.

Verificado: nuestra media sin ponderar sobre 30–2500 Hz era **−0.044 dB**, efectivamente clavada
a cero.

**Pero la hipótesis sólo explicaba ~25 % del problema:**

| Componente | dB |
|---|---|
| Convención de normalización (comprobado y corregido) | **0.98** |
| Offset residual sin explicar | **2.97** |
| Discrepancia real de forma (RMSE tras quitar todo offset) | **1.54** |
| Offset total original | 3.95 |

Es decir: corregir la convención acerca 1 dB, quedan ~3 dB de offset sin explicación y ~1.5 dB
de diferencia genuina de forma. **No lo voy a presentar como resuelto.**

Dado el hallazgo §1 (`N_eff` = 1.26), la explicación más probable es que ambas curvas están
estimando esa banda desde muy poca evidencia independiente, y cada método cae en un punto
distinto del espacio permitido por sus regularizaciones.

---

## 4. Lo que ya teníamos (no se tocó)

Verificado en el código antes de decidir:

| Técnica de V4.1 | Estado nuestro | Evidencia |
|---|---|---|
| Resta de piso de ruido con suelo conservador | **ya estaba** | `build_v10_2.py:252,261` |
| SNR calculado sobre la potencia **sin restar** | **ya estaba** | `snr=dbp((val+ε)/(noise+ε))` — la precaución de su §18 |
| Mediana ponderada robusta + MAD×1.4826 | **ya estaba** | `weighted_quantile`, `robust_scale` |
| Bootstrap a nivel de **pareja** | **ya estaba** | `bootstrap(obs, lc, 120)` |
| Leave-one-pair-out | **ya estaba** | selección de λ |
| Máscara de cuerdas al aire | **ya estaba** (corte duro en 300 Hz) | `build_v10_2.py:295,325` |

### Donde nuestro pipeline es más fuerte

| Aspecto | Nosotros | V4.1 |
|---|---|---|
| Reproducibilidad | **bit-idéntica** verificada | no la reporta |
| Estimador espectral | multitaper DPSS | Hann (su §11, §51.6) |
| F0 | refinamiento ±3.5 % **en uso** | guiada por etiqueta, el refinador **no se llama** (su §15.2, §51.3) |
| Offsets cuerda/registro/fase | **estimados** en el ajuste conjunto | multiplicadores heurísticos 0.62/0.55/0.85 (su §32) |
| Leave-one-family / leave-one-string | **integrados** | reconoce que no lo están (su §51.8) |
| Trazabilidad | manifiesto con commit y hashes | seed únicamente |

Sus multiplicadores heurísticos y nuestros offsets estimados llegan a la misma conclusión física
por caminos distintos:

```text
B-E-A menos D-G-C     V4.1 (heurístico)  -1.52 dB
                      nuestro V11 (estimado)  -3.48 dB
```

Mismo signo y mismo sentido; magnitud distinta. La nuestra sale de los datos, la suya de una
constante elegida, así que la diferencia no es sorprendente.

---

## 5. Lo que se adoptó (implementado en `improve_v12.py`)

### 5.1 Tamaño de muestra efectivo de Kish — **adoptado, alto valor**

Ver §1. Es el cambio más informativo de toda la revisión.

### 5.2 Neutralidad energética — **adoptado, alto valor**

La curva V11 **quitaba 0.974 dB de energía** al espectro de referencia del Café. Ese nivel
estaba escondido dentro de la curva en lugar de estar en el gain.

Se construye el espectro de referencia con las tomas de Café **con trastes** (las al aire llevan
el color de la cejuela, que ya se descuenta por otra vía), se mide el efecto energético de la
curva y se traslada al gain.

Resultado: gain **−12.04 dB**, que ahora coincide con la medición directa (−12.17) y con V4.1
(−11.94). Ese hueco de 1.1 dB que teníamos queda cerrado.

### 5.3 Peso por número de ciclos — **adoptado, valor medio**

```text
tonal:   clip((duración × frecuencia − 4) / 8, 0, 1)
ataque:  clip((duración × frecuencia − 2) / 5, 0, 1)
```

Teníamos `cycles_cafe` calculado y **sólo lo usábamos para un gráfico**
(`build_v10_2.py:291,634`). Ahora pesa.

Efecto: **1939 observaciones (6 %) quedan a peso cero** por tener menos de 4 ciclos, casi todas
subgraves en ventanas cortas. El gain **no se movió** (−11.062 → −11.065 dB), lo que dice que
esas observaciones no lo estaban sesgando, pero sí ensuciaban la curva grave.

Esto es la respuesta cuantitativa a por qué añadir puntos de rejilla no mejora el subgrave: a
30 Hz, en una ventana de 165 ms caben ~5 ciclos y ninguna densidad espectral lo arregla.

### 5.4 Umbrales de SNR por región — **adoptado, valor medio**

Antes: un umbral por **tipo de observación** (8 / 10 / 14 dB).
Ahora: por **región espectral**, más exigente hacia arriba (10 / 9 / 8 / 10 / 12 / 14 dB).

Los medios pagan menos porque llevan más energía y repiten mejor; los agudos pagan más porque
ahí es fácil confundir ruido con brillo.

### 5.5 Prior de códec graduado — **adoptado, valor medio**

Antes: corte binario en 15 kHz.
Ahora: 1.00 hasta 8 kHz, 0.92, 0.72, 0.45, 0.20, y 0.08 sobre 17 kHz.

Un realce ultraagudo necesita ahora mucha más evidencia antes de convertirse en recomendación.

### 5.6 Penalización de red eléctrica — **adoptado, valor bajo pero correcto**

Gaussiana de 40 cents alrededor de 50 / 100 / 150 Hz, factor 0.72, **sólo cuando el SNR local
baja de 18 dB**. No es un notch: 50 y 100 Hz también pueden ser contenido musical real.

Efecto: **457 observaciones** afectadas.

### 5.7 Transición suave de cuerdas al aire 280–300 Hz — **adoptado pero inoperante**

Implementado, pero **no cambia nada: 0 observaciones afectadas**. Nuestro pipeline ya descarta
duro el contenido de cuerdas al aire sobre 300 Hz **aguas arriba**, en la extracción
(`build_v10_2.py:295-298,325-326`), así que no queda nada que suavizar.

Para adoptarlo de verdad habría que modificar la extracción y re-extraer desde el audio. Queda
pendiente y **no cuenta como mejora todavía**.

### 5.8 Contracción continua por fiabilidad — **implementado, NO adoptado como entregable**

Media geométrica ponderada de soporte, N efectivo, SNR y anchura del bootstrap, por prior de
códec, suavizada a 1/12 de octava, con la constante aditiva resuelta para mantener neutralidad.

**Con los umbrales de V4.1 la fiabilidad mediana nos sale 0.105**, frente a las medianas de
0.54–0.74 que ellos reportan. Contraería la curva a un máximo de **1.25 dB** frente a 2.85 dB
del diagnóstico: la aplanaría.

La causa es el propio §1: `effective_score` tiene mediana **0.000** porque `N_eff` = 1.26.

Se publica como columna `recommended_db` y `reliability`, pero **el entregable sigue siendo
`energy_neutral_db`**. Los umbrales necesitan calibrarse contra nuestro nivel real de soporte
antes de usar esa curva, y hacerlo a ojo para que "quede bonita" sería exactamente el tipo de
ajuste que esta auditoría intenta evitar.

---

## 6. Lo que no se adoptó todavía

| Técnica | Por qué se posterga |
|---|---|
| Ancho de suavizado elegido por validación held-out por región, con regla de parsimonia (el más suave dentro de 0.08 dB) | Sustituye nuestra selección de λ. Es una idea buena y encaja con lo que ya vimos: los 8 candidatos de λ difieren <0.08 en score. Requiere reestructurar la regularización. |
| Desacuerdo ataque–sustain como reductor de confianza | Necesita meter las observaciones de ataque en el ajuste. Es nuestro P2-1: hoy se calculan y se descartan. |
| Lectura broad/narrow mezclada por proximidad armónica | Cambio profundo del estimador espectral. Nuestro DPSS ya cumple una función parecida. |
| Multiplicadores físicos heurísticos (0.62 / 0.55 / 0.85) | **No se adopta a propósito.** Nosotros ya *estimamos* esos offsets. Reemplazar una estimación por una constante sería un retroceso. |
| Rejilla de 912 puntos | La densidad no es el cuello de botella. Su propio informe lo dice y nuestro `N_eff` = 1.26 lo confirma. |

---

## 7. En qué coinciden los dos análisis

Vale registrarlo, porque son conclusiones independientes:

1. La diferencia de nivel es de **≈ −12 dB** y es del instrumento.
2. Nivel y timbre **deben** reportarse separados.
3. El **sustain** debe dominar en medios; el ataque en agudos.
4. El Azul tiene **más presencia en medios altos** (aunque discrepe la magnitud).
5. El grupo grave **B-E-A tiene menor salida relativa**.
6. Las cuerdas al aire **no deben** determinar la curva sobre 300 Hz.
7. La confianza **cae** sobre 10 kHz por el AAC.
8. **Más puntos de rejilla no es el próximo salto científico.** Lo es mejorar la evidencia:
   WAV sin comprimir, salida DI, varias dinámicas y posiciones de ataque, y validación auditiva
   ciega.

Sobre el punto 8, nuestro `N_eff` = 1.26 lo hace todavía más urgente: el límite no es el
procesamiento, son **16 parejas de grabaciones**.

---

## 8. Artefactos nuevos

```text
modules/emulate_azul/code/improve_v12.py     etapa de adopciones
CURVAS_DENSAS_V12.csv                        diagnóstico / neutral / recomendada + soporte Kish
FIABILIDAD_V12.csv                           los factores de confianza por separado
PESOS_EVIDENCIA_V12.csv                      peso por observación con cada factor
COMPARACION_V12_VS_V41.csv                   contraste externo en los 6 puntos publicados
RESUMEN_V12.json                             resumen de la corrida
```

---

## 9. Efecto neto sobre el proyecto

| Magnitud | Antes | Después |
|---|---|---|
| Gain vs medición directa | 1.11 dB de discrepancia | **0.13 dB** |
| Gain vs V4.1 | 1.10 dB | **0.10 dB** |
| Soporte real por frecuencia | `pair_count` = 3 (engañoso) | **`N_eff` = 1.26 (real)** |
| Observaciones sin ciclos suficientes | contadas, ignoradas | **1939 a peso cero** |
| Zona ultraaguda | corte binario en 15 kHz | prior graduado |
| Contaminación de red | no considerada | 457 observaciones descontadas |

Lo que **no** se resolvió: la discrepancia de ~3 dB de offset y ~1.5 dB de forma en presencia
frente a V4.1. Con `N_eff` = 1.26 en esa banda, dudo que se resuelva sin grabaciones nuevas.

**Sigue en pie la recomendación de no regenerar los presets MOOER**, que apoyan +15.5 dB en
3637 Hz sobre la región menos sostenida de todo el análisis.
