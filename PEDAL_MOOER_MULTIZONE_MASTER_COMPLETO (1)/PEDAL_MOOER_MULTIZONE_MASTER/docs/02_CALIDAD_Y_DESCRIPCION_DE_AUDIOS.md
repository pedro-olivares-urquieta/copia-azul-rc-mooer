# Calidad y significado de los audios

Los ocho archivos son AAC-LC estéreo a 44,1 kHz. Los canales son efectivamente duplicados; la conversión a mono por promedio no elimina información independiente. No se encontró clipping digital ni true peak cercano a 0 dBFS.

| Archivo | Duración | Peak | True peak 4× | RMS | LUFS aprox. | Crest |
|---|---:|---:|---:|---:|---:|---:|
| `1 22k rc bass on.m4a` | 84.68 s | -11.70 | -11.70 | -20.13 | -16.8 | 8.44 |
| `1 22k rc guitar on.m4a` | 90.19 s | -13.18 | -13.17 | -24.36 | -16.5 | 11.18 |
| `1 22k rc hybrid on.m4a` | 91.56 s | -13.54 | -13.52 | -24.17 | -17.2 | 10.64 |
| `1 22k.m4a` | 83.62 s | -26.81 | -26.81 | -32.68 | -28.8 | 5.88 |
| `Pink rc bass on.m4a` | 35.32 s | -16.68 | -16.66 | -31.74 | -30.7 | 15.06 |
| `Pink rc guitar on.m4a` | 38.61 s | -23.08 | -23.03 | -37.85 | -34.0 | 14.76 |
| `Pink rc hybrid on.m4a` | 37.24 s | -21.86 | -21.81 | -36.53 | -33.4 | 14.66 |
| `Pink.m4a` | 34.25 s | -30.79 | -30.72 | -44.76 | -42.9 | 13.97 |

## Etiquetado y barridos

La inspección detectó cuatro pasadas en cada archivo de barrido, dos ascendentes y dos descendentes. No apareció evidencia suficiente para declarar un archivo mal etiquetado. Las tres curvas ON son distintas y compatibles con los nombres Bajo, Híbrido y Guitarra.

## Linealidad

La forma rosa/barrido coincide con diferencia mediana absoluta de aproximadamente 0,10–0,15 dB tras retirar un offset global documentado. Esto es compatible con un sistema aproximadamente lineal en magnitud. El proxy armónico exploratorio no es una medición THD calibrada y queda marcado como inconcluso; no se usa para ajustar los presets.

## Límites

- Nyquist: 22,05 kHz.
- Alta/media confianza: hasta 15,5 kHz.
- 15,5–18 kHz: regularizado y baja confianza.
- 18–22,05 kHz: solo auditoría.
- 22,05–30 kHz: no medible.
