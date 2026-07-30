# PROMPT MAESTRO DEFINITIVO V10.2

## Extracción de máxima fidelidad de la función de transferencia Café → Azul mediante análisis tiempo–frecuencia adaptativo, matching inteligente e identificación estadística

---

# 0. Rol técnico

Actúa como un equipo multidisciplinario especializado en:

* Procesamiento digital de señales.
* Análisis acústico de bajos eléctricos de rango extendido.
* Estimación no paramétrica de funciones de transferencia.
* Análisis tiempo–frecuencia multirresolución.
* Seguimiento de frecuencia fundamental y parciales.
* Modelos sinusoidales y sinusoidal–residual.
* Análisis avanzado de ataques y decaimientos.
* Alineación musical y matching de eventos.
* Estadística robusta y jerárquica.
* Inferencia de incertidumbre.
* Validación cruzada agrupada.
* Psicoacústica.
* Prevención de sobreajuste y subajuste.
* Diseño y validación de ecualización estática.
* Evaluación de audio procesado.
* Reproducibilidad científica.

Debes reanalizar desde los audios originales todas las parejas del Bajo Café y el Bajo Azul para extraer la función de transferencia Café → Azul más fiel posible.

La V10.2 debe mejorar especialmente:

1. La resolución entre 20 y 60 Hz.
2. La identificación entre frecuencia y cuerda.
3. El muestreo y seguimiento de medios agudos y agudos.
4. La detección y comparación de ataques.
5. El matching temporal entre ejecuciones.
6. La separación entre contenido tonal, transiente y ruido.
7. El análisis de los espacios, silencios y superposiciones entre notas.
8. La validación local de la EQ sobre audios realmente procesados.

No debes limitar la salida principal a un shelf ni a una pequeña cantidad de filtros.

La salida principal será una curva continua de alta resolución llamada:

> **V10.2 PRECISE**

Las aproximaciones paramétricas se calcularán únicamente después de extraer esta curva.

---

# 1. Problemas que V10.2 debe resolver

V10.1 mejoró la zona 20–60 Hz, pero dejó asuntos pendientes:

* La corrección subgrave calculada es muy pequeña y sus intervalos incluyen 0 dB.
* Cuerda y frecuencia siguen parcialmente confundidas.
* La zona superior a 120 Hz reutilizó observaciones intermedias de V9.
* PRECISE mejoró la tendencia central, pero V9 mantuvo mejores P90 y P95.
* El máximo de aproximadamente +5,67 dB entre 800 Hz y 1,6 kHz necesita una auditoría independiente.
* El análisis temporal aún puede tratar de manera demasiado parecida graves lentos y agudos rápidos.
* El matching puede mejorar utilizando información temporal, espectral, armónica y de envolvente simultáneamente.
* El análisis de agudos debe aumentar su resolución sin convertir ruido de dedos o de interfaz en brillo real.

V10.2 debe resolver estos puntos sin asumir que las conclusiones de V9 o V10.1 son correctas.

---

# 2. Objetivo matemático

Estima:

[
H(f)=Azul(f)-Café(f)
]

La convención obligatoria es:

* (H(f)>0): elevar esa frecuencia en el Café.
* (H(f)<0): reducir esa frecuencia en el Café.

Separa:

[
H_{\text{total}}(f)=G+Q(f)
]

donde:

* (G): diferencia global de nivel.
* (Q(f)): diferencia tímbrica común reproducible mediante EQ.

Además, separa explícitamente:

[
D_{j,s,r,p}(f,t)
================

G
+
S_s
+
R_r
+
F_j
+
P_p(f,t)
+
Q(f)
+
\epsilon
]

donde:

* (S_s): desviación particular de la cuerda.
* (R_r): desviación asociada al registro.
* (F_j): efecto de pareja o familia.
* (P_p(f,t)): diferencia temporal de ataque, cuerpo, sustain o decaimiento.
* (Q(f)): curva EQ estática común.
* (\epsilon): residuo no explicado.

No permitas que:

* El gain global absorba la forma del subgrave.
* Los offsets por cuerda absorban automáticamente diferencias de frecuencia.
* La EQ absorba diferencias puramente temporales.
* El ataque determine por sí solo la curva de sustain.
* El ruido residual determine la curva de agudos.

---

# 3. No confiar ciegamente en la descripción del usuario

La descripción de cada ejercicio es una orientación superficial.

No debes confiar ciegamente en:

* El nombre del archivo.
* La cuerda indicada.
* El traste indicado.
* La nota indicada.
* El tempo declarado.
* La subdivisión rítmica.
* La cantidad de ataques.
* El orden de las notas.
* La descripción de la cromática.
* La identificación de los acordes.
* La afirmación de que dos archivos son equivalentes.
* Las causas físicas sugeridas por el usuario.
* La interpretación del usuario sobre ruido, brillo o fundamentales.

La jerarquía de evidencia será:

1. Señal medida directamente.
2. Coherencia musical.
3. Correspondencia comprobable entre Café y Azul.
4. Repetibilidad entre eventos y familias.
5. Metadatos y nombres.
6. Descripción del usuario.

Clasifica cada afirmación como:

* Confirmada.
* Probable.
* Ambigua.
* Contradicha.
* No comprobable.

No fuerces la señal para que coincida con la descripción.

---

# 4. Reextracción completa desde los audios originales

La curva final V10.2 debe recalcularse completamente desde los audios originales entre 20 Hz y 20 kHz.

No utilices como entrada final:

* Curvas suavizadas de V9.
* Puntos agregados de V9.
* Curvas suavizadas de V10.1.
* Máscaras de soporte previamente seleccionadas.
* Observaciones que hayan perdido trazabilidad por evento.
* Ponderaciones elegidas para justificar un modelo anterior.

Se permite reutilizar únicamente:

* WAV decodificados y verificados.
* Inventario técnico.
* Metadatos.
* Segmentaciones que vuelvan a validarse.
* Cachés espectrales sin reducción, si conservan trazabilidad completa.

Todo elemento reutilizado debe conservar:

* Archivo original.
* Hash.
* Evento.
* Tiempo.
* Ventana.
* Sample rate.
* Método.
* Resolución.
* Parámetros.
* Versión del extractor.

La extracción espectral, ponderación, ajuste, validación y selección deben volver a ejecutarse.

---

# 5. Inventario y control técnico

Para cada archivo inspecciona:

* Formato.
* Sample rate.
* Canales.
* Duración.
* Codificación.
* Compresión con pérdida.
* Canales duplicados.
* Clipping.
* DC offset.
* Silencios.
* Cortes abruptos.
* Latencia.
* Tonos eléctricos.
* Ruido estacionario.
* Golpes mecánicos.
* Artefactos de codec.
* Posibles errores de nombre.

Conserva los originales intactos.

Si los canales son idénticos, convierte a mono de forma documentada.

No apliques silenciosamente:

* High-pass.
* Low-cut.
* Noise gate.
* Compresión.
* Limitación.
* Normalización por archivo.
* De-noise destructivo.

Si aplicas un filtro contra DC, informa su respuesta exacta en:

* 20 Hz.
* 25 Hz.
* 30,87 Hz.
* 41,20 Hz.
* 55 Hz.
* 60 Hz.

---

# 6. Auditoría semántica de los ejercicios

Antes de entrenar la EQ, determina qué contiene realmente cada archivo.

Audita:

* Número real de ataques.
* Tiempo de cada ataque.
* Frecuencia fundamental.
* Nota probable.
* Cuerda probable.
* Traste o registro.
* Tempo efectivo.
* Subdivisión.
* Dobles ataques.
* Notas repetidas.
* Notas omitidas.
* Eventos adicionales.
* Resonancias simpatéticas.
* Cuerdas no apagadas.
* Superposición entre notas.
* Ruido de dedos.
* Ruido de traste.
* Contenido polifónico.
* Correspondencia Café–Azul.

Genera una tabla con:

* Archivo.
* Clasificación nominal.
* Clasificación inferida.
* Cuerda.
* Nota o secuencia.
* Registro.
* Eventos detectados.
* Tempo.
* Confianza.
* Discrepancias.
* Regiones utilizables.
* Fases utilizables.
* Decisión de uso.
* Justificación.

No excluyas archivos ni eventos silenciosamente.

---

# 7. Principio tiempo–frecuencia adaptativo

No analices todas las frecuencias con la misma duración de ventana.

Los graves tienen periodos largos y evolucionan más lentamente en milisegundos.

Los agudos tienen periodos cortos y permiten observar cambios más rápidos.

La duración de análisis debe depender de:

* Frecuencia.
* Número de ciclos.
* Fase temporal.
* SNR.
* Duración disponible.
* Separación respecto del siguiente ataque.

Utiliza una familia de ventanas cuya longitud aproximada siga:

[
T(f)=\operatorname{clip}\left(\frac{N_{\text{ciclos}}(f)}{f},
T_{\min},
T_{\max}\right)
]

No utilices un único (N_{\text{ciclos}}) ni una única ventana para todo el espectro.

El número de ciclos debe optimizarse según la zona y la tarea.

---

# 8. Ventanas adaptativas por región

Utiliza inicialmente estas familias de candidatos y selecciónalas mediante validación:

## 20–60 Hz

* Ventanas largas.
* Aproximadamente 8–24 ciclos cuando la duración lo permita.
* Combinación de varias repeticiones cuando una nota individual sea demasiado corta.
* Estimadores sinusoidales paramétricos.
* Prioridad en cuerpo y sustain.

## 60–150 Hz

* Aproximadamente 6–18 ciclos.
* Ventanas suficientemente largas para separar fundamentales y parciales cercanos.
* Seguimiento temporal de amplitud.

## 150–500 Hz

* Aproximadamente 4–12 ciclos.
* Resolución equilibrada entre tiempo y frecuencia.

## 500 Hz–2 kHz

* Aproximadamente 3–10 ciclos.
* Ventanas más breves durante el ataque y más largas durante el cuerpo.

## 2–5 kHz

* Ventanas cortas e intermedias.
* Prioridad en ataque, articulación y parciales.
* Seguimiento de componentes tonales frente a ruido.

## 5–10 kHz

* Ventanas muy cortas para transientes.
* Ventanas intermedias para detectar contenido tonal persistente.
* Control estricto de SNR.

## 10–20 kHz

* Análisis principalmente transitorio y residual.
* No asumir que existe sustain musical.
* Exigir evidencia repetible en varias parejas.

Estos valores son candidatos, no reglas rígidas.

Debes comparar varias longitudes y seleccionar las que mejor generalicen.

---

# 9. Herramientas avanzadas de análisis tiempo–frecuencia

No dependas de una sola STFT.

Utiliza y cruza:

## 9.1 STFT multirresolución

Con varias longitudes de ventana y solapamientos.

## 9.2 Multitaper

Usa tapers DPSS cuando ayuden a reducir varianza y leakage.

## 9.3 CQT o VQT

Con alta resolución en bins por octava para observar estructura musical y parciales.

## 9.4 Transformada wavelet continua

Utiliza wavelets apropiadas para estudiar ataques y evolución temporal por frecuencia.

## 9.5 Synchrosqueezing

Cuando sea estable, emplea transformadas wavelet o STFT reasignadas para concentrar energía alrededor de trayectorias tonales.

## 9.6 Espectrograma reasignado

Úsalo para mejorar la localización de ataques y componentes breves.

## 9.7 Modelado sinusoidal

Estima frecuencia, amplitud, fase y decaimiento de fundamentales y parciales.

## 9.8 Demodulación compleja o heterodinación

Especialmente para B0, E1, A1 y otros componentes graves.

## 9.9 Cepstrum y harmonic summation

Úsalos como apoyo para evitar errores de octava.

## 9.10 ESPRIT, MUSIC u otros estimadores de alta resolución

Pueden utilizarse cuando:

* El SNR sea suficiente.
* El número de componentes sea estable.
* La selección de orden esté validada.
* No produzcan picos artificiales.

No uses herramientas avanzadas solo por su nombre.

Cada método debe demostrar:

* Estabilidad.
* Mejora de resolución.
* Correspondencia con la señal.
* Ausencia de artefactos.

---

# 10. Muestreo espectral refinado

La malla interna completa debe tener al menos:

* 4.096 puntos logarítmicos entre 20 Hz y 20 kHz.

Además, utiliza mallas locales de alta densidad alrededor de:

* Fundamentales.
* Parciales medidos.
* Picos candidatos.
* Valles candidatos.
* Cambios de pendiente.
* Zona 800 Hz–1,6 kHz.
* Zona 2–8 kHz.

Entre 20 y 120 Hz utiliza como mínimo:

* 512 puntos logarítmicos.

Entre 2 y 12 kHz utiliza una malla híbrida:

* Logarítmica para estructura general.
* Lineal o adaptativa alrededor de parciales y transientes.

No confundas una malla densa con más evidencia.

Cada punto debe incluir:

* Valor central.
* Incertidumbre.
* SNR.
* Número efectivo de parejas.
* Número de cuerdas.
* Número de familias.
* Estado de identificación.
* Método dominante.
* Origen del valor.

---

# 11. Refinamiento especial de agudos

La V10.2 debe analizar con mayor detalle:

* 2–3 kHz.
* 3–4 kHz.
* 4–5 kHz.
* 5–6,3 kHz.
* 6,3–8 kHz.
* 8–10 kHz.
* 10–12,5 kHz.
* 12,5–16 kHz.
* 16–20 kHz.

Dentro de cada zona utiliza subregiones adaptativas.

No reduzcas 2–8 kHz a tres o cuatro puntos.

Para cada rasgo agudo informa:

* Frecuencia central.
* Ancho.
* Amplitud.
* Duración temporal.
* Presencia en ataque.
* Presencia en cuerpo.
* Presencia en sustain.
* Naturaleza tonal o residual.
* Número de parejas.
* Número de cuerdas.
* Dependencia de una sola toma.
* Intervalo de confianza.

No suavices automáticamente un pico y un valle próximos hasta convertirlos en una pendiente.

---

# 12. Separación tonal–transiente–residual

Divide la señal en:

## Componente tonal

Fundamental y parciales estables.

## Componente transitoria

Ataques, clicks, roce inicial, púa o dedos.

## Componente residual

Ruido, leakage, aire, ruido eléctrico y componentes no tonales.

Puedes utilizar:

* Modelado sinusoidal–residual.
* Harmonic–percussive separation adaptada.
* Median filtering tiempo–frecuencia.
* Seguimiento de trayectorias sinusoidales.
* Coherencia temporal de fase.
* Spectral flatness.
* Kurtosis espectral.
* Modulación temporal.

La EQ tímbrica principal debe depender preferentemente de:

* Componente tonal.
* Parte reproducible del transiente.
* Residuo repetible con relación clara al instrumento.

No permitas que un golpe aislado o ruido de dedo determine un boost de agudos.

---

# 13. Análisis avanzado del ataque

No definas el ataque mediante una ventana fija universal.

Para cada evento y banda calcula:

* Tiempo de onset.
* Pendiente inicial.
* Tiempo hasta el máximo.
* Tiempo de subida.
* Duración del transiente.
* Energía máxima.
* Centro temporal del ataque.
* Centroide espectral del ataque.
* Flujo espectral.
* Cambio de fase.
* Coherencia de fase.
* Distribución de energía por banda.
* Tiempo de estabilización tonal.

El ataque debe analizarse como una superficie:

[
A(f,t)
]

No como un único espectro promedio.

Genera mapas de diferencia Café–Azul de:

* 0–5 ms.
* 5–10 ms.
* 10–20 ms.
* 20–40 ms.
* 40–80 ms.
* 80–160 ms.

Estas ventanas deben adaptarse cuando el registro lo requiera.

En los graves, la estabilización tonal puede tardar decenas o cientos de milisegundos.

En agudos, los cambios importantes pueden ocurrir en pocos milisegundos.

---

# 14. Ataque dependiente de frecuencia

Para cada frecuencia o banda estima:

* Momento de aparición.
* Momento de máximo.
* Tiempo de decaimiento.
* Duración sobre el piso de ruido.
* Proporción ataque/cuerpo.
* Proporción transiente/tonal.

No compares directamente:

* El ataque de 5 kHz usando una ventana de 300 ms.
* La fundamental de 31 Hz usando una ventana de 5 ms.

Crea dos representaciones paralelas:

## Resolución por milisegundos

Adecuada para comparar sincronía y transientes.

## Resolución por ciclos

Adecuada para comparar componentes tonales de distintas frecuencias.

La interpretación final debe cruzar ambas.

---

# 15. Análisis del espacio entre notas

Audita los espacios temporales entre ataques:

* Inter-onset interval.
* Duración efectiva de cada nota.
* Silencio entre eventos.
* Solapamiento.
* Cola de decaimiento.
* Resonancia de la nota anterior.
* Ruido entre ataques.
* Notas que se pisan entre sí.
* Diferencias de tempo local.
* Anticipaciones o retrasos.

No uses una ventana de sustain si contiene:

* El ataque de la nota siguiente.
* La cola de una nota anterior no equivalente.
* Ruido de manipulación.
* Un silencio con ruido de interfaz.

Genera una máscara de contaminación temporal por evento.

Clasifica cada tramo como:

* Ataque limpio.
* Cuerpo limpio.
* Sustain limpio.
* Solapamiento.
* Espacio silencioso.
* Ruido.
* Ambiguo.

---

# 16. Matching temporal inteligente

No emparejes eventos por índice.

El matching debe realizarse en etapas.

## Etapa 1: identidad musical

Compara:

* Fundamental.
* Nota.
* Orden musical.
* Posición en la secuencia.
* Registro.
* Cuerda probable.

## Etapa 2: posición rítmica

Compara:

* Tiempo relativo.
* Inter-onset interval.
* Tempo local.
* Desviación respecto de la grilla.

## Etapa 3: ataque

Compara:

* Forma de la envolvente.
* Flujo espectral.
* Distribución de energía.
* Tiempo al máximo.
* Relación transiente/tonal.

## Etapa 4: cuerpo y sustain

Compara:

* Fundamental.
* Parciales.
* Decaimiento.
* Duración.
* Estabilidad.

Utiliza alineación monotónica con:

* Inserciones.
* Eliminaciones.
* Repeticiones.
* Eventos adicionales.
* Penalizaciones por saltos musicales.

Puedes emplear:

* Dynamic time warping restringido.
* Soft-DTW.
* Programación dinámica.
* Optimal transport temporal regularizado.
* Emparejamiento bipartito con orden.
* Hidden Markov models para secuencias.

No permitas que una herramienta de matching altere el orden musical arbitrariamente.

---

# 17. Matching dependiente de frecuencia

Después de emparejar el evento musical, realiza alineación fina separada por bandas.

Los componentes graves, medios y agudos pueden alcanzar su máximo en momentos distintos.

Calcula alineaciones para:

* 20–60 Hz.
* 60–150 Hz.
* 150–500 Hz.
* 500 Hz–2 kHz.
* 2–5 kHz.
* 5–10 kHz.

No desplaces físicamente cada banda para construir un audio artificial.

Usa estas alineaciones únicamente para comparar características equivalentes.

Informa:

* Desplazamiento de onset.
* Desplazamiento del máximo.
* Diferencia de tiempo de estabilización.
* Diferencia de decaimiento.
* Incertidumbre.

---

# 18. Representaciones avanzadas para el matching

Construye descriptores multiescala con:

* Envolventes por banda.
* Fundamental.
* Distribución armónica.
* Spectral flux.
* Mel o Bark energies solo como apoyo.
* CQT.
* Modulación temporal.
* Scattering transform tiempo–frecuencia cuando esté disponible.
* Embeddings acústicos únicamente como diagnóstico, no como verdad.

El costo de matching debe combinar:

[
C =
w_n C_{\text{nota}}
+
w_t C_{\text{tiempo}}
+
w_a C_{\text{ataque}}
+
w_h C_{\text{armónicos}}
+
w_d C_{\text{decaimiento}}
]

Los pesos deben seleccionarse mediante validación y auditoría.

No optimices los pesos para obtener la curva más conveniente.

---

# 19. Seguimiento de fundamentales y parciales

Para cada evento estima:

* Fundamental real.
* Amplitud.
* Fase.
* Deriva de afinación.
* Estabilidad.
* Decaimiento.
* Parciales.
* Inarmonicidad.
* SNR individual.
* Duración del parcial.

No midas cada armónico únicamente en un múltiplo exacto.

Usa una región adaptativa alrededor de la frecuencia esperada.

Distingue:

* Parcial tonal.
* Resonancia.
* Componente transitoria.
* Ruido.
* Leakage.
* Artefacto de codec.

---

# 20. Envolvente armónica relativa

Calcula:

[
R_{i,k}=L_{i,k}-L_{i,1}
]

y:

[
\Delta R_{i,k}
==============

R_{Azul,i,k}-R_{Café,i,k}
]

La forma EQ debe utilizar principalmente diferencias armónicas relativas para evitar que el nivel de la fundamental domine el timbre.

Conserva también:

* Diferencia absoluta.
* Energía por banda.
* Energía tonal.
* Energía transitoria.
* Energía residual.

Cada parcial debe tener un peso basado en:

* SNR.
* Energía.
* Estabilidad.
* Repetibilidad.
* Confianza de matching.
* Fase temporal.
* Independencia estadística.

---

# 21. Prioridad 20–60 Hz

Analiza independientemente:

* B0 alrededor de 30,87 Hz.
* E1 alrededor de 41,20 Hz.
* A1 alrededor de 55 Hz.
* B1 alrededor de 61,74 Hz como ancla adicional.

No impongas las frecuencias nominales.

Mide la afinación real de cada evento.

Utiliza:

* Regresión sinusoidal.
* Demodulación compleja.
* Goertzel adaptativo.
* Multitaper.
* Ajuste exponencial del decaimiento.
* Estimación sub-bin.
* Seguimiento de fase.

Calcula por fundamental:

* Ataque.
* Estabilización.
* Cuerpo.
* Sustain.
* Decaimiento.
* Número de ciclos.
* SNR.
* Incertidumbre.

Entre 20 y 28 Hz, si no existe señal tonal suficiente, marca la región como no identificada.

---

# 22. Regla de cuerdas al aire

Las cuerdas al aire pueden entrenar la EQ común hasta 300 Hz.

Sobre 300 Hz:

* Peso cero en el entrenamiento principal.
* Conservación diagnóstica.
* No pueden decidir presencia o brillo.

Bajo 300 Hz no debes reducir artificialmente su importancia.

En particular:

* B al aire es central para aproximadamente 31 Hz.
* E al aire es central para aproximadamente 41 Hz.
* A al aire es central para aproximadamente 55 Hz.

---

# 23. Identificabilidad cuerda–frecuencia

Antes de atribuir una diferencia a una cuerda o a una frecuencia, construye una matriz con:

* Frecuencia.
* Nota.
* Cuerda.
* Traste.
* Registro.
* Familia.
* Repeticiones.
* Misma nota en otras cuerdas.
* Otras notas medidas en la misma cuerda.

Clasifica:

* Identificable.
* Parcialmente identificable.
* Fuertemente confundido.
* No identificable.

Ajusta tres modelos:

## FREQUENCY

Atribuye la diferencia principalmente a la respuesta en frecuencia.

## STRING

Atribuye la diferencia principalmente al balance por cuerda.

## JOINT

Reparte la diferencia mediante un modelo jerárquico.

Compara:

* Validación.
* Incertidumbre.
* Correlación de parámetros.
* Sensibilidad a regularización.
* Curva resultante.

Si los modelos tienen rendimiento equivalente y producen curvas diferentes, declara la región como no identificable.

---

# 24. Ganancia global

Calcula el gain a partir de:

* Fundamentales.
* Energía tonal.
* Cuerpo.
* Sustain.
* Acordes auditados.
* Estadísticos por pareja.

Resume jerárquicamente:

1. Evento.
2. Pareja.
3. Cuerda.
4. Registro.
5. Familia.

No permitas que la cromática domine por cantidad de eventos.

Entrega:

* Gain global.
* Intervalo.
* Gain por cuerda.
* Gain por registro.
* Gain por familia.
* Gain por pareja.
* Outliers.
* Sensibilidad del gain a los distintos modelos.

---

# 25. Auditoría especial de 800 Hz–1,6 kHz

La loma principal debe recalcularse directamente desde los originales.

Audita:

* 630 Hz.
* 800 Hz.
* 1 kHz.
* 1,25 kHz.
* 1,6 kHz.
* 2 kHz.

Para cada frecuencia entrega:

* Valor central.
* Intervalo de confianza.
* Parejas efectivas.
* Cuerdas.
* Familias.
* Registros.
* Ataque.
* Cuerpo.
* Sustain.
* Armónicos absolutos.
* Armónicos relativos.
* Con y sin cromática.
* Con y sin C traste 24.
* Con y sin acordes.
* Al retirar la pareja más influyente.

No mantengas automáticamente +5,67 dB si depende de una sola fuente.

---

# 26. Construcción de la curva empírica

Primero calcula una curva:

## V10.2 RAW

Debe mostrar la estimación empírica con mínimo suavizado.

Por frecuencia entrega:

* Mediana ponderada.
* Media robusta.
* Distribución.
* Intervalo.
* SNR.
* Número efectivo de observaciones.
* Influencia máxima.
* Estado.

RAW no será necesariamente un preset, pero permitirá ver toda la estructura disponible.

---

# 27. Construcción de las curvas robustas

Genera:

## V10.2 PRECISE-CENTRAL

Optimizada para:

* MAE.
* Mediana.
* RMSE central.
* Cantidad de parejas mejoradas.
* Fidelidad local típica.

## V10.2 PRECISE-ROBUST

Optimizada para:

* P90.
* P95.
* Peor pareja.
* Peor cuerda.
* Prevención de degradaciones.

## V10.2 SAFE

Versión conservadora con mayor regularización.

## V10.2 PARAMETRIC

Aproximación posterior mediante filtros prácticos.

## V10.2 NO-SUB

Igual a PRECISE, pero sin correcciones 20–60 Hz.

## V10.2 NO-HIGH

Igual a PRECISE, pero sin correcciones superiores a una frecuencia de corte auditada, por ejemplo 4 u 8 kHz.

Estas ablaciones deben demostrar cuánto aporta cada zona.

---

# 28. Métodos no paramétricos

Compara:

* Spline adaptativo.
* LOESS robusto.
* Gaussian process.
* Trend filtering.
* Total variation de segundo orden.
* Penalización de curvatura adaptativa.
* Modelo bayesiano continuo.
* Ensemble de estimadores.

La regularización debe depender de:

* SNR.
* Densidad de evidencia.
* Incertidumbre.
* Estabilidad entre folds.
* Número de familias.

Más soporte permite más detalle.

Menos soporte exige más regularización.

Ausencia de soporte exige clasificación como no identificado.

---

# 29. Preservación de rasgos locales

Para cada pico, valle o cambio de pendiente calcula:

* Frecuencia central.
* Ancho.
* Amplitud.
* Intervalo.
* Parejas.
* Cuerdas.
* Familias.
* Fase temporal.
* Estabilidad.
* Influencia dominante.

Conserva un rasgo cuando:

* Aparece en varias fuentes independientes.
* Mantiene dirección entre folds.
* Supera razonablemente su incertidumbre.
* No coincide con ruido.
* Mejora validación local.
* Mejora los audios procesados.

No elimines un rasgo solamente porque un shelf tenga RMSE parecido.

No conserves un rasgo únicamente porque aparece en RAW.

---

# 30. Validación cruzada

Realiza:

## Leave-one-pair-out

Retira una pareja completa.

## Leave-one-family-out

Retira:

* Cuerdas al aire.
* Traste 12.
* Cromática.
* Acordes.
* Registro agudo.

## Leave-one-string-out

Retira una cuerda completa.

## Leave-one-register-out

Retira un registro completo.

## Leave-one-repetition-block-out

Retira bloques temporales completos.

## Bootstrap jerárquico

Remuestrea:

* Familias.
* Parejas.
* Bloques.
* Eventos.

No remuestrees bins o ventanas como observaciones independientes.

---

# 31. Validación del matching

La calidad del matching debe validarse independientemente de la EQ.

Calcula:

* Error de nota.
* Error de orden.
* Desplazamiento temporal.
* Diferencia de inter-onset interval.
* Costo de ataque.
* Costo armónico.
* Costo de decaimiento.
* Confianza.

Realiza una auditoría manual o visual de una muestra representativa:

* B al aire.
* E al aire.
* A al aire.
* Traste 12.
* C traste 24.
* Cromática.
* Am7.
* Cmaj7.

Genera gráficos superpuestos de:

* Onsets.
* Envolventes.
* Fundamentales.
* Ataques.
* Cuerpos.
* Decaimientos.

No continúes silenciosamente con matches de baja confianza.

---

# 32. Significancia de PRECISE frente a NO-SUB y NO-HIGH

Calcula mediante bootstrap pareado:

[
\Delta E_{\text{sub}}
=====================

E_{\text{NO-SUB}}-E_{\text{PRECISE}}
]

[
\Delta E_{\text{high}}
======================

E_{\text{NO-HIGH}}-E_{\text{PRECISE}}
]

Entrega:

* Media.
* Mediana.
* IC 95 %.
* Probabilidad de mejora.
* Probabilidad de superar 0,1 dB.
* Probabilidad de superar 0,25 dB.
* Probabilidad de superar 0,5 dB.

No afirmes que una zona aporta una mejora real si el intervalo incluye 0 de forma amplia.

---

# 33. Métricas globales y locales

Calcula:

* RMSE.
* MAE.
* Mediana.
* P75.
* P90.
* P95.
* Peor pareja.
* Parejas mejoradas.
* Parejas empeoradas.

Y por región:

* 20–40 Hz.
* 40–60 Hz.
* 60–100 Hz.
* 100–160 Hz.
* 160–250 Hz.
* 250–400 Hz.
* 400–630 Hz.
* 630 Hz–1 kHz.
* 1–1,6 kHz.
* 1,6–2,5 kHz.
* 2,5–4 kHz.
* 4–6,3 kHz.
* 6,3–8 kHz.
* 8–12 kHz.
* 12–16 kHz.
* 16–20 kHz.

Y por fase:

* Ataque.
* Estabilización.
* Cuerpo temprano.
* Cuerpo tardío.
* Sustain.
* Decaimiento.

---

# 34. Regla de no degradación

Una curva no podrá recomendarse como principal si:

* Mejora la mediana pero empeora fuertemente P95.
* Produce una degradación grave en una cuerda.
* Empeora repetidamente una familia.
* Mejora medios destruyendo subgraves.
* Mejora sustain destruyendo ataques.
* Mejora la métrica espectral pero empeora los renders.

Construye una frontera de Pareto entre:

* Error central.
* Error extremo.
* Error subgrave.
* Error de medios.
* Error de agudos.
* Complejidad.
* Estabilidad.

---

# 35. Validación mediante renders reales

Para cada pareja genera:

* Café original.
* Café PRECISE-CENTRAL.
* Café PRECISE-ROBUST.
* Café SAFE.
* Café PARAMETRIC.
* Café NO-SUB.
* Café NO-HIGH.
* Azul original.

Genera comparaciones:

* Alternadas.
* Estéreo alineado.
* Ataque aislado.
* Cuerpo.
* Sustain.
* 20–80 Hz.
* 20–120 Hz.
* 2–8 kHz.
* Full-band.

No utilices las versiones filtradas como único criterio auditivo.

Vuelve a medir los audios renderizados con el pipeline completo.

---

# 36. Iteración residual

Después de aplicar V10.2:

1. Calcula el residuo.

2. Separa residuo tonal, transitorio y ruidoso.

3. Determina si el residuo:

   * Aparece en varias cuerdas.
   * Aparece en varias familias.
   * Es estable.
   * Tiene suficiente SNR.
   * Mejora en validación.

4. Añade una corrección únicamente cuando generalice.

No iteres hasta eliminar el error de entrenamiento.

Entrega:

* V10.2.0.
* Residuo.
* Corrección candidata.
* V10.2.1.
* Razón de aceptación o rechazo.

---

# 37. Estados de soporte

Cada frecuencia debe clasificarse como:

## Medido robustamente

Evidencia repetible e independiente.

## Medido con incertidumbre

Evidencia real, pero dispersa.

## Inferido localmente

Interpolación entre regiones respaldadas.

## Regularizado

Valor conservador por bajo soporte.

## No identificado

Información insuficiente.

Distingue siempre:

* 0 dB medido.
* 0 dB compatible con incertidumbre.
* 0 dB regularizado.
* Región no identificada.

---

# 38. Entregables numéricos

Exporta curvas densas con al menos 2.048 puntos y preferentemente 4.096:

* V10.2 RAW.
* PRECISE-CENTRAL.
* PRECISE-ROBUST.
* SAFE.
* PARAMETRIC.
* NO-SUB.
* NO-HIGH.

Cada fila debe contener:

* Frecuencia.
* Valor de cada curva.
* Límite inferior.
* Límite superior.
* SNR.
* Parejas efectivas.
* Cuerdas.
* Familias.
* Influencia máxima.
* Estado.
* Origen.
* Estabilidad.
* Resolución temporal utilizada.
* Resolución espectral utilizada.

---

# 39. Entregables específicos de tiempo y matching

Genera:

* MATCHING_EVENTOS_V10_2.csv
* MATCHING_BANDAS_V10_2.csv
* ATAQUES_MULTIESCALA_V10_2.csv
* ESPACIOS_Y_SOLAPAMIENTOS_V10_2.csv
* VENTANAS_ADAPTATIVAS_V10_2.csv
* TRAYECTORIAS_FUNDAMENTALES_V10_2.csv
* TRAYECTORIAS_ARMONICAS_V10_2.csv
* MAPA_TIEMPO_FRECUENCIA_DIFERENCIAL.csv
* AUDITORIA_MATCHING_V10_2.md
* AUDITORIA_ATAQUES_V10_2.md
* AUDITORIA_AGUDOS_V10_2.md

---

# 40. Entregables de identificabilidad

Genera:

* MATRIZ_IDENTIFICABILIDAD_CUERDA_FRECUENCIA.csv
* COMPARACION_FREQUENCY_STRING_JOINT.csv
* CORRELACION_EQ_OFFSETS_CUERDA.csv
* SIGNIFICANCIA_PRECISE_VS_NO_SUB.csv
* SIGNIFICANCIA_PRECISE_VS_NO_HIGH.csv
* BOOTSTRAP_PAREADO_V9_V10_1_V10_2.csv
* AUDITORIA_800_1600_HZ.csv
* FRONTERA_PARETO_CENTRAL_ROBUST.csv

---

# 41. Gráficos obligatorios

Genera:

1. Curvas completas RAW, PRECISE-CENTRAL, PRECISE-ROBUST y SAFE.

2. Curva 20–120 Hz ampliada.

3. Curva 2–12 kHz ampliada.

4. Mapa tiempo–frecuencia de ataques.

5. Diferencia de ataques Café–Azul por milisegundos.

6. Tiempo de estabilización por frecuencia.

7. Duración de ventanas utilizadas.

8. Resolución por frecuencia.

9. Matching de eventos.

10. Espacios, solapamientos y silencios.

11. Trayectorias de fundamentales.

12. Trayectorias armónicas.

13. Curva por cuerda.

14. Curva por familia.

15. Ataque, cuerpo y sustain.

16. Soporte por frecuencia.

17. SNR.

18. Influencia de observaciones.

19. V9, V10.1 y V10.2 con métricas recalculadas mediante el mismo pipeline.

20. PRECISE frente a NO-SUB.

21. PRECISE frente a NO-HIGH.

22. P90/P95 frente a mediana.

23. Distribución bootstrap.

---

# 42. Informes obligatorios

Entrega:

* INFORME_TECNICO_AUTONOMO_V10_2.md
* INFORME_ANALISIS_TIEMPO_FRECUENCIA.md
* INFORME_MATCHING_INTELIGENTE.md
* INFORME_ATAQUES_MULTIESCALA.md
* INFORME_REFINAMIENTO_AGUDOS.md
* INFORME_ESPECIALIZADO_20_60_HZ.md
* INFORME_IDENTIFICABILIDAD.md
* INFORME_VALIDACION.md
* INFORME_SIGNIFICANCIA_PRACTICA.md
* INFORME_REGIONES_NO_IDENTIFICADAS.md
* INFORME_COMPARACION_V9_V10_1_V10_2.md

Todos deben ser autónomos y trazables.

---

# 43. Estructura de la respuesta final

## 1. Veredicto general

Describe la transferencia sin reducirla prematuramente a un shelf.

## 2. Qué contienen realmente los audios

Explica las correcciones a la descripción inicial.

## 3. Calidad del matching

Indica cuántos eventos fueron:

* Emparejados.
* Rechazados.
* Dudosos.
* Insertados.
* Omitidos.

## 4. Comportamiento temporal

Explica:

* Ataque.
* Estabilización.
* Cuerpo.
* Sustain.
* Decaimiento.
* Espacio entre notas.

## 5. Subgraves

Explica B0, E1 y A1 y la confusión cuerda–frecuencia.

## 6. Medios

Audita especialmente 800 Hz–1,6 kHz.

## 7. Agudos

Distingue:

* Contenido tonal.
* Ataque.
* Ruido de dedos.
* Residuo.
* Región no identificada.

## 8. Curvas recomendadas

Presenta:

* PRECISE-CENTRAL.
* PRECISE-ROBUST.
* SAFE.
* PARAMETRIC.

## 9. Gain

Entrega gain y offsets con incertidumbre.

## 10. Validación

Incluye métricas centrales, extremas, locales y temporales.

## 11. Comparación con V9 y V10.1

Todas recalculadas con el mismo pipeline.

## 12. Limitaciones

Explica qué no puede resolver una EQ estática.

## 13. Archivos entregados

Lista completa.

---

# 44. Criterio de honestidad

Debes evitar simultáneamente:

## Sobreajuste

* Seguir ruido.
* Seguir un golpe aislado.
* Convertir roce de dedos en brillo.
* Dibujar picos donde no existe soporte.
* Interpretar una sola pareja como evidencia común.

## Subajuste

* Reducir todo a un shelf.
* Usar una sola ventana para todas las frecuencias.
* Ignorar los graves por ser lentos.
* Ignorar los agudos por ser breves.
* Promediar ataques y sustains hasta perder diferencias.
* Eliminar rasgos locales repetibles.

No confundas:

* Milisegundos con ciclos.
* Resolución gráfica con resolución real.
* Zero-padding con información nueva.
* Falta de señal con 0 dB.
* Offset de cuerda con respuesta en frecuencia.
* Ataque con sustain.
* Ruido con brillo.
* Cantidad de ventanas con evidencia independiente.
* Una mejora de 0,05 dB con una mejora relevante.
* Una curva regularizada con una medición.

La V10.2 debe analizar cada frecuencia con el tiempo que físicamente necesita.

Los graves deben observarse durante más ciclos y más milisegundos.

Los agudos deben analizarse con ventanas más rápidas y seguimiento preciso de transientes.

La curva principal debe integrar inteligentemente estas escalas sin obligarlas a compartir la misma resolución temporal.

No pidas confirmación.

Comienza desde los audios originales, audita el matching y reconstruye completamente la transferencia 20 Hz–20 kHz.
