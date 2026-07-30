# Resumen ejecutivo

La fuente de verdad fueron los ocho M4A originales. Las curvas previas se usaron únicamente como baseline histórico. Se reconstruyeron por separado ruido rosa y cuatro barridos, se fusionaron con pesos de confianza y se verificó convergencia entre 192 y 384 puntos por octava.

## Decisión final

No apareció una solución nueva que dominara inequívocamente a todos los presets históricos en todas las zonas. Por eso se aplicó el criterio de aceptación conservador solicitado: conservar el preset anterior cuando la mejora del peor error escondía degradaciones regionales mayores que la incertidumbre.

| Setup | Recomendación | Peor RMSE regional | Promedio regional | RMSE global ponderado | RMSE 20–60 Hz | Error 30 Hz |
|---|---|---:|---:|---:|---:|---:|
| Bajo | `[15.0, 3.5, -3.5, 16.0, -3.5]` | 0.699 | 0.458 | 0.437 | 0.248 | 0.195 |
| Híbrido | `[-1.5, 3.0, 4.0, 8.5, 1.5]` | 0.799 | 0.535 | 0.518 | 0.254 | 0.203 |
| Guitarra | `[-10.5, 5.5, 2.0, 10.5, 0.0]` | 0.714 | 0.423 | 0.427 | 0.106 | 0.079 |

- **Bajo:** se conserva el preset refinado anterior. El candidato minimax reduce el peor error, pero empeora Graves y Medios por encima de la incertidumbre.
- **Híbrido:** se conserva el preset refinado anterior por la misma razón; la alternativa minimax es válida para auditoría, no una superioridad global.
- **Guitarra:** sí se acepta un preset nuevo: `[-10,5; +5,5; +2,0; +10,5; 0,0] dB`, porque mejora el peor RMSE y el promedio sin degradaciones regionales mayores que la incertidumbre.

## Convergencia de resolución

Entre 20 Hz y 15,5 kHz, 192 y 384 PPO difieren aproximadamente 0,041 dB en Bajo, 0,045 dB en Híbrido y 0,048 dB en Guitarra. La divergencia crece en 15,5–18 kHz, confirmando que esa zona no debe dominar el ajuste.

## Principal limitación

La mayor pérdida de precisión no procede de la cuantización de 0,5 dB, sino de bloquear las cinco Q en 0,3. Permitir Q variable con las mismas frecuencias reduce el peor RMSE diagnóstico aproximadamente a 0,176 dB en Bajo, 0,400 dB en Híbrido y 0,274 dB en Guitarra.
