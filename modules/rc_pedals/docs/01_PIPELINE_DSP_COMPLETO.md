# Pipeline DSP autónomo

## Entradas y emparejamiento

Dos familias 1:1:

- Ruido rosa: `Pink.m4a` OFF y tres tomas ON.
- Barridos: `1 22k.m4a` OFF y tres tomas ON.

## Control de calidad

1. SHA-256, códec, sample rate, canales, duración y bitrate.
2. Peak, true peak 4×, RMS, LUFS aproximado, crest factor y DC.
3. Correlación L/R y diferencia RMS entre canales.
4. Detección de clipping, dropouts y tramos útiles.
5. Conversión temporal a float64 y mono por promedio L/R; no se normaliza cada archivo.

## Ruido rosa

- Ventana estable detectada por RMS.
- Bloques de 4 s, hop 2 s.
- Seis tapers DPSS, NW 3,5.
- Mediana robusta y bootstrap.
- Curva ON/OFF absoluta.

## Barridos

- Detección de cuatro pasadas: up1, down1, up2, down2.
- STFT para extraer la cresta real.
- Ajuste robusto de frecuencia instantánea.
- Demodulación síncrona por frecuencia.
- SNR local, offsets de pasada y mediana robusta.

## Fusión

- El ruido rosa ancla el gain absoluto.
- Los barridos aportan forma y repetibilidad.
- Alineación global barrido→rosa documentada.
- Pesos inversos a incertidumbre, SNR y confianza de borde.
- Dos iteraciones Huber para rechazar artefactos exclusivos de un método.

## Resoluciones y suavizado

- 192 PPO principal.
- 384 PPO para convergencia.
- 1/24, 1/12, 1/6 y 1/3 de octava.
- La curva recomendada utiliza 1/12 y continuación regularizada desde 15,5 kHz.

## Optimización

- Grilla logarítmica, cinco regiones con igual peso agregado.
- Modelo calibrado MOOER, no biquad ideal.
- 30.000 candidatos discretos aleatorios por setup, DE, annealing, coordinate descent y cubos locales.
- Evaluación final a 192 PPO.
- Frontera Pareto: peor RMSE regional, promedio regional, RMSE global, P95 y subgrave.
- Las soluciones se denominan “mejores encontradas y verificadas localmente”, no óptimos globales.

## Robustez

Monte Carlo con variación de curva objetivo, fusión, suavizado y un escenario diagnóstico de tolerancias del modelo MOOER. Las tolerancias internas no fueron medidas directamente y están etiquetadas como supuestos de escenario.

## Reproducción

```bash
python code/01_audio_reconstruction_and_384_audit.py
python code/02_multizone_discrete_optimization.py
python code/03_constraint_diagnostics.py
python code/04_operational_selection.py
python code/05_comparison_by_region.py
```
