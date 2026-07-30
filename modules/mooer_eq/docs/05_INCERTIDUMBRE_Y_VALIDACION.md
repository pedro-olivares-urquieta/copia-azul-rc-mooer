# Robustez, incertidumbre y validación independiente

## Monte Carlo

Se variaron la mezcla rosa/barrido, el suavizado, ruido correlacionado según incertidumbre y un escenario diagnóstico de calibración MOOER. Las desviaciones de calibración no son tolerancias oficiales ni fueron medidas en varias unidades; se usan para stress testing.

| Setup | MC peor RMSE P95 | MC global P95 | P95 de error P95 |
|---|---:|---:|---:|
| Bajo | 0.922 | 0.606 | 1.165 |
| Híbrido | 0.997 | 0.585 | 1.249 |
| Guitarra | 0.994 | 0.489 | 1.239 |

## Validación cruzada

Se entrenó con rosa y validó con barridos, y viceversa. También se ejecutó leave-one-pass-out. Bajo es el más estable; Híbrido presenta mayor dispersión en barridos; Guitarra tiene pasadas con artefactos fuertes, especialmente en validación individual, por lo que la curva fusionada y el bootstrap son esenciales.

## 192 frente a 384 PPO

La convergencia es mejor que 0,05 dB RMS hasta 15,5 kHz. La discrepancia sobre esa frecuencia se reporta como incertidumbre de borde, no como detalle adicional real.

## Suavizado

Los presets recomendados cambian poco entre 1/24 y 1/12. El suavizado 1/3 reduce métricas porque elimina estructura, pero no se usa como fuente principal para evitar una apariencia artificialmente favorable.
