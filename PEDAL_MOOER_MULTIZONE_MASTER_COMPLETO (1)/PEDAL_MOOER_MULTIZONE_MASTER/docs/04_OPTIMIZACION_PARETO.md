# Informe de optimización y Pareto

## Función objetivo

Objetivo primario: reducir el peor RMSE regional entre Subgraves, Graves, Medios, Presencia y Brillo confiable. Objetivo secundario: promedio equilibrado de las cinco zonas. Objetivos terciarios: RMSE global ponderado, P95, pendiente, RMSE 25–40 Hz y error en 30 Hz.

## Algoritmos comparados

- Differential Evolution continuo y cuantización.
- Muestreo discreto multiarranque.
- Simulated annealing.
- Coordinate descent.
- Cubos locales ±1,5 dB.
- Filtro Pareto y Monte Carlo.

El espacio completo contiene 65^5 combinaciones. No se afirma óptimo global. La búsqueda registró semillas y verificó localmente los candidatos finales.

## Decisión de aceptación

Un candidato no reemplaza al anterior si la mejora del peor RMSE se compra con degradaciones regionales mayores que la incertidumbre. Esta regla conservó Bajo e Híbrido y permitió aceptar Guitarra.

## Global libre diagnóstico

Con los gains recomendados, el barrido de global −60…+3 dB vuelve a seleccionar +3 dB en los tres setups; por ello se mantiene la arquitectura principal.
