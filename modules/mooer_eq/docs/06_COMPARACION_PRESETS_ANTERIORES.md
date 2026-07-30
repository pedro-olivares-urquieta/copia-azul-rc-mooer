# Comparación obligatoria con presets anteriores

## Resumen

| Setup | Preset | Peor RMSE | Promedio | Global | 20–60 Hz | Error 30 Hz |
|---|---|---:|---:|---:|---:|---:|
| Bajo | previous | 0.699 | 0.458 | 0.437 | 0.248 | 0.195 |
| Bajo | recommended | 0.699 | 0.458 | 0.437 | 0.248 | 0.195 |
| Bajo | minimax_audit | 0.575 | 0.469 | 0.499 | 0.255 | 0.292 |
| Bajo | subgrave | 0.713 | 0.435 | 0.483 | 0.043 | 0.015 |
| Bajo | global | 0.699 | 0.458 | 0.437 | 0.248 | 0.195 |
| Híbrido | previous | 0.799 | 0.535 | 0.518 | 0.254 | 0.203 |
| Híbrido | recommended | 0.799 | 0.535 | 0.518 | 0.254 | 0.203 |
| Híbrido | minimax_audit | 0.723 | 0.540 | 0.594 | 0.062 | 0.002 |
| Híbrido | subgrave | 0.793 | 0.603 | 0.669 | 0.033 | 0.023 |
| Híbrido | global | 1.138 | 0.501 | 0.463 | 0.126 | 0.004 |
| Guitarra | previous | 0.890 | 0.440 | 0.416 | 0.085 | 0.130 |
| Guitarra | recommended | 0.714 | 0.423 | 0.427 | 0.106 | 0.079 |
| Guitarra | minimax_audit | 0.619 | 0.478 | 0.499 | 0.301 | 0.241 |
| Guitarra | subgrave | 0.708 | 0.534 | 0.601 | 0.052 | 0.006 |
| Guitarra | global | 0.988 | 0.433 | 0.403 | 0.109 | 0.011 |

## Cambios frente a incertidumbre

La tabla `data/improvement_vs_measurement_uncertainty.csv` marca las zonas donde el cambio absoluto supera la incertidumbre mediana. Bajo e Híbrido no tienen un candidato nuevo que reduzca el peor error sin degradar otras regiones por encima de ese umbral. Guitarra sí.

## Alternativa puntual 30 Hz

Los presets de prioridad puntual reducen el error exacto en 30 Hz, pero no dominan las métricas multizona. Se conservan únicamente como alternativas especializadas.
