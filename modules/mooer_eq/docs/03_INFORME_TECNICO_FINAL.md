# Informe técnico final

## Diagnóstico del pipeline anterior

El pipeline anterior era sólido en reconstrucción, pero la selección final dependía demasiado de RMSE global o del error puntual en 30 Hz. Esto podía ocultar intercambios grandes entre regiones. La revisión introdujo RMSE por zona con igual peso agregado, minimax regional, Pareto, comparación contra incertidumbre y una regla de no sustitución cuando la mejora no domina al preset existente.

## Presets recomendados

### Bajo

| Frecuencia | Gain | Q mostrado | Q efectivo |
|---:|---:|---:|---:|
| 30 Hz | +15.0 dB | 0,3 | 0.159 |
| 148 Hz | +3.5 dB | 0,3 | 0.168 |
| 735 Hz | -3.5 dB | 0,3 | 0.173 |
| 3637 Hz | +16.0 dB | 0,3 | 0.158 |
| 18000 Hz | -3.5 dB | 0,3 | 0.173 |

| Región | RMSE | MAE | Sesgo | P95 | Máximo |
|---|---:|---:|---:|---:|---:|
| Subgraves | 0.248 | 0.218 | +0.214 | 0.343 | 0.346 |
| Graves | 0.374 | 0.327 | -0.224 | 0.574 | 0.583 |
| Medios | 0.405 | 0.361 | +0.198 | 0.605 | 0.607 |
| Presencia | 0.561 | 0.525 | -0.525 | 0.771 | 0.805 |
| Brillo | 0.699 | 0.590 | +0.565 | 1.241 | 1.398 |

- Peor RMSE regional: **0.699 dB**.
- Promedio regional: **0.458 dB**.
- RMSE global ponderado: **0.437 dB**.
- RMSE 20–60 Hz: **0.248 dB**.
- Error exacto en 30 Hz: **0.195 dB**.
- Monte Carlo P95 del peor RMSE: **0.922 dB**.

### Híbrido

| Frecuencia | Gain | Q mostrado | Q efectivo |
|---:|---:|---:|---:|
| 30 Hz | -1.5 dB | 0,3 | 0.172 |
| 148 Hz | +3.0 dB | 0,3 | 0.168 |
| 735 Hz | +4.0 dB | 0,3 | 0.168 |
| 3637 Hz | +8.5 dB | 0,3 | 0.164 |
| 18000 Hz | +1.5 dB | 0,3 | 0.170 |

| Región | RMSE | MAE | Sesgo | P95 | Máximo |
|---|---:|---:|---:|---:|---:|
| Subgraves | 0.253 | 0.250 | +0.250 | 0.333 | 0.339 |
| Graves | 0.311 | 0.266 | -0.094 | 0.535 | 0.562 |
| Medios | 0.579 | 0.518 | +0.273 | 0.885 | 0.900 |
| Presencia | 0.735 | 0.677 | -0.672 | 0.982 | 1.007 |
| Brillo | 0.799 | 0.646 | +0.522 | 1.473 | 1.740 |

- Peor RMSE regional: **0.799 dB**.
- Promedio regional: **0.535 dB**.
- RMSE global ponderado: **0.518 dB**.
- RMSE 20–60 Hz: **0.254 dB**.
- Error exacto en 30 Hz: **0.203 dB**.
- Monte Carlo P95 del peor RMSE: **0.997 dB**.

### Guitarra

| Frecuencia | Gain | Q mostrado | Q efectivo |
|---:|---:|---:|---:|
| 30 Hz | -10.5 dB | 0,3 | 0.179 |
| 148 Hz | +5.5 dB | 0,3 | 0.166 |
| 735 Hz | +2.0 dB | 0,3 | 0.169 |
| 3637 Hz | +10.5 dB | 0,3 | 0.163 |
| 18000 Hz | +0.0 dB | 0,3 | 0.171 |

| Región | RMSE | MAE | Sesgo | P95 | Máximo |
|---|---:|---:|---:|---:|---:|
| Subgraves | 0.106 | 0.094 | +0.012 | 0.180 | 0.193 |
| Graves | 0.152 | 0.132 | -0.017 | 0.255 | 0.284 |
| Medios | 0.437 | 0.372 | +0.241 | 0.716 | 0.729 |
| Presencia | 0.714 | 0.664 | -0.664 | 1.057 | 1.087 |
| Brillo | 0.707 | 0.599 | +0.477 | 1.299 | 1.458 |

- Peor RMSE regional: **0.714 dB**.
- Promedio regional: **0.423 dB**.
- RMSE global ponderado: **0.427 dB**.
- RMSE 20–60 Hz: **0.106 dB**.
- Error exacto en 30 Hz: **0.079 dB**.
- Monte Carlo P95 del peor RMSE: **0.994 dB**.

## Alternativas

Cada setup incluye una alternativa subgrave y una variante de menor RMSE global para auditoría. En Bajo, la variante global coincide con la recomendada. Las variantes minimax se conservan, pero no sustituyen automáticamente a los presets operativos por las degradaciones regionales descritas.

## Tratamiento de 30 Hz

La frontera Pareto demuestra que reducir el error puntual en 30 Hz puede trasladar error hacia Graves, Medios, Presencia o Brillo. La alternativa subgrave se recomienda solamente cuando 20–60 Hz sea más importante que el equilibrio total. No se impuso una tolerancia artificial de ±0,02 dB.

## Incertidumbre

Las medianas de incertidumbre objetivo están cerca de 0,084–0,088 dB en graves/medios bajos y aumentan a 0,12–0,18 dB en presencia/brillo. Los cambios de preset se compararon contra estas cifras antes de aceptar una sustitución.

## Limitaciones del MOOER

La descomposición diagnóstica muestra que la cuantización de 0,5 dB añade solo una fracción del error: al liberar continuamente los gains, el peor RMSE baja aproximadamente 0,03–0,05 dB. En cambio, liberar Q con las mismas frecuencias produce mejoras mucho mayores. Por tanto, la restricción dominante es Q 0,3 y, en segundo lugar, la colocación fija de las frecuencias. El global +3 dB no limita estos tres resultados: el barrido diagnóstico de global libre vuelve a seleccionar +3 dB.

## Conclusiones explícitas

- Mejor preset equilibrado Bajo: el refinado anterior, conservado.
- Mejor preset equilibrado Híbrido: el refinado anterior, conservado.
- Mejor preset equilibrado Guitarra: el nuevo `[-10,5; +5,5; +2,0; +10,5; 0,0]`.
- El error inevitable procede principalmente del Q extremadamente ancho y las frecuencias bloqueadas.
- La cuantización de 0,5 dB es secundaria.
- La incertidumbre de audio es pequeña en 20 Hz–2 kHz y mayor en presencia/brillo.
- La banda limitante en Bajo es Brillo; en Híbrido es Brillo/Presencia; en Guitarra es Presencia/Brillo.
- La prioridad extrema de 30 Hz no sigue siendo beneficiosa al considerar todo el espectro; funciona como alternativa, no como recomendación universal.
- Solo Guitarra presenta una solución nueva que supera suficientemente al preset anterior bajo la regla conservadora.
