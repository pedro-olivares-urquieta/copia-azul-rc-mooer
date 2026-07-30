# INFORME TÉCNICO AUTÓNOMO V10.2

## 1. Veredicto general
Gain global recomendado: **-10.59 dB** (IC95 -11.80 a -8.36 dB). Fundamental-only: -11.52 dB; energía-only: -9.67 dB. V10.2 fue reextraída desde los WAV originales 20 Hz–20 kHz mediante matching monotónico, estimación individual de F0, multitaper DPSS, parciales relativos, ventanas temporales adaptadas y separación explícita de observaciones tonales y residuales.

La curva principal no se reduce a un shelf: conserva únicamente rasgos que sobreviven validación agrupada y soporte independiente.

## 2. Qué contienen realmente los audios
| pair        | family    | declared_kind   |   events_cafe |   events_azul |   matched |   tempo_cafe |   tempo_azul | classification   | decision                  |
|:------------|:----------|:----------------|--------------:|--------------:|----------:|-------------:|-------------:|:-----------------|:--------------------------|
| B_open      | open      | mono            |           104 |           108 |        97 |     100.349  |      99.8641 | confirmed        | training                  |
| E_open      | open      | mono            |           103 |           102 |        92 |     100.349  |      99.8641 | confirmed        | training                  |
| A_open      | open      | mono            |           104 |           102 |        91 |      99.8641 |      99.8641 | confirmed        | training                  |
| D_open      | open      | mono            |           104 |           118 |        31 |      99.8641 |      99.8641 | partial          | training                  |
| G_open      | open      | mono            |           104 |           111 |        89 |     100.349  |      99.8641 | confirmed        | training                  |
| C_open      | open      | mono            |           104 |           113 |        78 |      99.8641 |     100.349  | confirmed        | training                  |
| B_12        | fret12    | mono            |            52 |            55 |        44 |      99.8641 |      99.8641 | confirmed        | training                  |
| E_12        | fret12    | mono            |            56 |            56 |        50 |      99.8641 |      99.8641 | confirmed        | training                  |
| A_12        | fret12    | mono            |            53 |            63 |        16 |     100.349  |      99.6235 | partial          | training                  |
| D_12        | fret12    | mono            |            77 |            55 |         3 |      99.8641 |     100.838  | partial          | training                  |
| G_12        | fret12    | mono            |            55 |            53 |        48 |     100.593  |      99.8641 | confirmed        | training                  |
| C_12        | fret12    | mono            |            55 |            52 |        48 |     100.106  |     100.349  | confirmed        | training                  |
| C_24        | high      | mono            |            51 |            50 |        32 |      99.384  |      99.8641 | partial          | training                  |
| C_chromatic | chromatic | chromatic       |           100 |           100 |        88 |     198.768  |     201.677  | confirmed        | training                  |
| Am7         | chord     | chord           |            49 |            45 |        35 |      99.8641 |      99.6235 | confirmed        | validation/reduced weight |
| Cmaj7       | chord     | chord           |            55 |            45 |        31 |      99.8641 |      99.6235 | partial          | validation/reduced weight |

La cromática fue auditada como 100 eventos correspondientes a células solapadas hasta 25–28; los eventos se alinearon por identidad musical, tiempo y descriptores acústicos. Las cuerdas al aire tienen peso cero sobre 300 Hz.

## 3. Calidad del matching
Eventos emparejados: **873**. Costo mediano: **1.580**. Matches de baja confianza: **167**. No se forzaron eventos omitidos.

## 4. Comportamiento temporal
Ataque, estabilización, cuerpo, sustain y decaimiento fueron modelados por separado. Los graves utilizan más ciclos y ventanas más largas; los mapas de ataque usan 0–5, 5–10, 10–20, 20–40, 40–80 y 80–160 ms. La EQ estática se pondera principalmente por cuerpo y sustain.

## 5. Subgraves
B0, E1 y A1 conservan medición directa, pero cuerda y frecuencia siguen parcialmente confundidas. La comparación FREQUENCY/STRING/JOINT se entrega por separado. Entre 20 y 28 Hz no existe evidencia tonal directa suficiente y la implementación se regulariza hacia 0 dB.

## 6. Medios
La zona 800 Hz–1,6 kHz fue reextraída desde los originales. Su amplitud final, intervalos, soporte y ablaciones aparecen en AUDITORIA_800_1600_HZ.csv; no se heredó el +5,67 dB de V10.1.

## 7. Agudos
La curva distingue parciales tonales, energía transitoria y residuo. El corte de soporte para la ablación NO-HIGH quedó en aproximadamente **8000 Hz**; sobre las regiones sin varias parejas independientes, el retorno a 0 dB es regularización, no una medición de igualdad.

## 8. Curvas recomendadas
|   frequency_hz |   precise_central_db |   precise_robust_db |      safe_db |   parametric_db |   ci95_low_db |   ci95_high_db | support_state            |
|---------------:|---------------------:|--------------------:|-------------:|----------------:|--------------:|---------------:|:-------------------------|
|        20      |          0.00143902  |        -0.000311546 |  0           |    -0.0148253   |  -0.00550921  |    0.00603977  | No identificado          |
|        27.9781 |          0.0108466   |         0.00359175  |  0.0037963   |    -0.0806566   |  -0.0120875   |    0.0336683   | No identificado          |
|        30.8538 |          0.00265993  |         0.000873297 |  0.000938879 |    -0.083473    |  -0.0297403   |    0.0432445   | Inferido localmente      |
|        41.1702 |         -0.0731702   |        -0.0480307   | -0.0271401   |     0.0673829   |  -0.121061    |    0.0259806   | Inferido localmente      |
|        55.0288 |         -0.290948    |        -0.26472     | -0.125588    |    -0.00271502  |  -0.405727    |    0.0345903   | Inferido localmente      |
|        80.0254 |         -0.882594    |        -0.864775    | -0.600164    |    -1.49013     |  -1.20253     |   -0.0497576   | Medido con incertidumbre |
|       119.964  |         -2.05089     |        -2.19975     | -1.8458      |    -2.52692     |  -2.51698     |   -0.428174    | Medido robustamente      |
|       249.881  |         -0.824471    |        -0.738869    | -0.364643    |    -0.920328    |  -1.45073     |    1.03388     | Medido robustamente      |
|       499.841  |         -1.68278     |        -1.74309     | -0.768659    |    -1.52609     |  -2.34027     |    1.57931     | Medido robustamente      |
|       629.794  |         -1.29342     |        -1.26037     | -0.540083    |    -1.35722     |  -1.95636     |    1.29144     | Medido con incertidumbre |
|       800.254  |         -0.133438    |        -0.105118    | -0.0511279   |    -0.208738    |  -0.850413    |    0.959534    | Medido robustamente      |
|       999.841  |          1.3262      |         1.32145     |  0.949807    |     1.56381     |  -0.336734    |    1.67838     | Medido robustamente      |
|      1249.21   |          2.83719     |         2.851       |  2.12975     |     3.20052     |  -0.144022    |    3.07717     | Medido con incertidumbre |
|      1600.76   |          4.06031     |         4.16715     |  3.50548     |     3.93116     |  -0.144553    |    4.19423     | Medido robustamente      |
|      2000      |          3.93659     |         3.91296     |  3.39551     |     3.61125     |  -0.145106    |    4.11711     | Medido robustamente      |
|      2498.81   |          3.3961      |         3.3319      |  2.5546      |     2.95222     |  -0.168739    |    3.76118     | Medido con incertidumbre |
|      3148.47   |          2.35783     |         2.31062     |  2.05668     |     2.26647     |  -0.0823335   |    3.18439     | Medido robustamente      |
|      4000.63   |          0.922755    |         0.904842    |  0.621889    |     1.5203      |  -0.0198954   |    2.14998     | Medido con incertidumbre |
|      4998.41   |          0.0665937   |         0.0653869   |  0.0372528   |     0.839885    |  -0.0296648   |    1.20218     | Medido con incertidumbre |
|      6297.94   |         -0.0488698   |        -0.0479066   | -0.0215419   |     0.336522    |  -0.0484962   |    0.507266    | Inferido localmente      |
|      8002.54   |         -0.00616453  |        -0.00604815  | -0.00233142  |     0.0913292   |  -0.006966    |    0.136235    | Inferido localmente      |
|      9998.41   |          0.00246648  |         0.00241815  |  0.000435531 |     0.0193744   |  -0.00160338  |    0.0146919   | Inferido localmente      |
|     12492.1    |          0.000330702 |         0.000325556 |  0           |     0.00295262  |  -0.00182418  |    0.000339912 | Medido con incertidumbre |
|     16007.6    |         -2.67367e-05 |        -2.61046e-05 | -0           |     0.000245625 |  -2.8807e-05  |    0.000102305 | Inferido localmente      |
|     20000      |          3.18052e-06 |         3.10343e-06 |  0           |     1.85108e-05 |  -1.16958e-05 |    3.41713e-06 | No identificado          |

## 9. Gain y offsets por cuerda
| cuerda   |   offset_db |
|:---------|------------:|
| B        |  -2.64623   |
| E        |  -1.99285   |
| A        |   0.0837136 |
| D        |   2.80679   |
| G        |   0.858288  |
| C        |   0.890286  |

## 10. Validación
| model            |       MAE |      RMSE |     P90 |     P95 |
|:-----------------|----------:|----------:|--------:|--------:|
| V10_1            | nan       | nan       | 9.33435 | 12.125  |
| V10_2_CENTRAL    |   3.8695  |   5.69621 | 8.21244 | 11.4772 |
| V10_2_NO_HIGH    |   3.8695  |   5.69621 | 8.21245 | 11.4772 |
| V10_2_NO_SUB     |   3.87368 |   5.69944 | 8.21126 | 11.506  |
| V10_2_PARAMETRIC |   3.92554 |   5.73656 | 8.30441 | 11.5958 |
| V10_2_ROBUST     |   3.8731  |   5.69531 | 8.22311 | 11.4566 |
| V10_2_SAFE       |   3.83604 |   5.68412 | 8.19928 | 11.4697 |
| V9               | nan       | nan       | 9.59333 | 12.4649 |

## 11. Comparación con V9 y V10.1
Las curvas V9 y V10.1 se reevalúan sobre las observaciones V10.2, con los parámetros de nivel/cuerda/fase reajustados. De este modo la comparación no usa las métricas históricas de pipelines diferentes.

## 12. Limitaciones
Una EQ estática no puede igualar offsets por cuerda, diferencias de ataque/decaimiento, balance de voces en acordes, ni componentes no lineales. Repeticiones de una misma toma reducen incertidumbre interna pero no equivalen a nuevas cuerdas o instrumentos independientes.

## 13. Reproducibilidad
No se aplicó high-pass, gate, compresión ni normalización por archivo. Se resta únicamente la media DC antes de análisis/render. Seed: 10202. Los filtros de render son FIR lineales de 8193 taps aplicados offline.

## Auditoría de correcciones internas

La primera ejecución V10.2 rechazó fundamentales y parciales por un estimador de SNR contaminado por leakage de la propia línea. Esos resultados no se conservaron. La versión final estima el piso desde silencios reales y vuelve a ajustar curva, gain, bootstrap, validación y renders.


## Comparación final con el mismo pipeline

| model            |   pairs |     MAE |    RMSE |   Median_MAE |     P90 |      P95 |   worst_pair |
|:-----------------|--------:|--------:|--------:|-------------:|--------:|---------:|-------------:|
| V10_2_SAFE       |      14 | 3.83604 | 5.68412 |      3.17143 | 8.19928 | 11.4697  |      8.19159 |
| V10_2_CENTRAL    |      14 | 3.8695  | 5.69621 |      3.21603 | 8.21244 | 11.4772  |      8.0607  |
| V10_2_NO_HIGH    |      14 | 3.8695  | 5.69621 |      3.21603 | 8.21245 | 11.4772  |      8.0607  |
| V10_2_ROBUST     |      14 | 3.8731  | 5.69531 |      3.21934 | 8.22311 | 11.4566  |      8.06172 |
| V10_2_NO_SUB     |      14 | 3.87368 | 5.69944 |      3.21603 | 8.21126 | 11.506   |      8.06006 |
| V10_2_PARAMETRIC |      14 | 3.92554 | 5.73656 |      3.48769 | 8.30441 | 11.5958  |      8.0761  |
| V10_1            |      14 | 3.98359 | 4.89692 |      4.15482 | 7.52739 |  8.88235 |      6.50697 |
| V9               |      14 | 4.14225 | 5.08318 |      4.14155 | 7.8366  |  9.23817 |      7.14755 |

NO-SUB y NO-HIGH no muestran una mejora práctica significativa frente a CENTRAL; sus intervalos pareados incluyen 0 y la probabilidad de superar 0,1 dB es 0.
