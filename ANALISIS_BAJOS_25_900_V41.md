# Análisis: subgraves / graves / medios bajos (25–900 Hz) — V4.1 vs nosotros

Operativa actual: `V20.0-operative` · `v19_presence_robust+v20_hard_10k`  
(V20 no toca ≤900 Hz; el shape bajo viene de V19/V17 pair-first.)

## Veredicto corto

**Acuerdo tonal con V4.1:** no hace falta un shelf enorme de subgrave; el cambio Café→Azul bajo 900 Hz crece hacia medios bajos.  
**Desacuerdo de magnitud:** ellos marcan ~**−0,76 dB @ 98 Hz** y ~**+3,49 dB @ 515 Hz**; nosotros **−1,73 @ 98** y **+1,56 @ 515** (pico medio-bajo más cerca de **+2,8 @ 400 Hz**).

| Región | Media operativa (dB) | Lectura |
|---|---:|---|
| 25–120 Hz | −0,91 | subgrave moderado / ligeramente negativo |
| 120–350 Hz | +0,94 | grave casi neutro → leve subida |
| 350–600 Hz | +2,40 | cuerpo / densidad (donde más se mueve) |
| 600–900 Hz | +0,83 | transición; menos boost que 350–600 |

Landmarks: 30,9 → −1,07 · 55 → −0,63 · 98 → −1,73 · 220 → +1,16 · 350 → +2,50 · 400 → +2,76 · 515 → +1,56 · 900 → +1,38.

## División funcional (adoptada conceptualmente)

| Región | Rango V4.1 | En nuestro código |
|---|---|---|
| Subgrave | 25–120 | `PHASE_MIX` + `SNR_THRESHOLDS` + smooth candidates |
| Grave | 120–350 | igual |
| Medio bajo | 350–900 | smooth V14 usa 350–900; fase parte 350–600 / 600–2500; SNR mete 350–2500 junto |

## Qué hace mejor V4.1 (bajos)

1. **Ventana `low` larga (60–760 ms, min 180 ms)** — nosotros mapeamos su peso 82 % a la fase **body** (~165 ms). A 30 Hz eso son ~5 ciclos vs ~21 con 700 ms: peor resolución de fundamental.
2. **Piso de ruido pre-onset + resta PSD** — `noise_profile()` se calcula en `extract_pair` y **no se usa** (resta local de sidebands sí).
3. **Umbrales de energía relativa −58 / −68 / −82 dB** — nosotros solo tenemos proxy SNR (`relative_energy_score` = √clip((snr−thr)/28)).
4. **Máscara open 280–300 efectiva** — tenemos rampa soft en `open_string_mask`, pero el extract hace **corte duro >300 Hz** → la rampa no actúa.
5. **Broad/narrow + blend por proximidad armónica** como estimador (nosotros: DPSS + parciales; no hay lectura broad/narrow de PSD).
6. **Split SNR 600–900** (ellos 8 dB ahí; nosotros 8 dB desde 350 hasta 2500).
7. **Narrativa física B–E–A / D–G–C** documentada (×0,62 / ×0,55) — útil como diagnóstico, no como EQ operativa.

## Qué hacemos mejor nosotros (bajos)

1. **DPSS multitaper** vs Hann único + FFT fija 32k.
2. **F0 refine cableado** (±3,5 % ≈ ±60 cents) en detección/eventos; V4.1 lo describe pero no lo conecta al núcleo.
3. **Matching acústico monotónico** + confianza de evento en pesos (no solo orden de onsets).
4. **Offsets string/register/phase estimados** en el fit — no multiplicadores fijos 0,62/0,55.
5. **Cycles + hum 50/100/150 + SNR regional** ya en el path operativo (`enrich_observations` V15→V19).
6. **Pair-first + mediana ponderada + MAD** sin aplanar con smooth LOO en la curva de copia.
7. **Neutralidad energética + gain ~−12,01 dB** (consenso con su −11,94).
8. **Métrica hold-out / render** Café+EQ vs Azul; la curva no se elige por “bonita” tras shrink.
9. **No adoptar** smooth ½ oct en subgrave ni `EQ×reliability` como deliverable (V12 `recommended` aplana 98/515 hacia 0).

## Ya teníamos del informe (bien cableado)

| Pieza V4.1 | Dónde |
|---|---|
| Pesos fase 82/16/2 · 38/52/10 · 8/74/18 · 0/74/26 | `improve_v14.PHASE_MIX` (body≈low) |
| Cycles `clip((dur·f−4)/8)` | `improve_v12.cycles_score` |
| SNR 10 / 9 / 8 dB + score /18 | `improve_v12.SNR_THRESHOLDS` |
| Hum 50/100/150 ×0,72 si SNR&lt;18 | `improve_v12.mains_factor` (σ=40¢ vs 28¢ V4.1) |
| Open &gt;300 fuera | hard-cut extract + máscara soft (inerte) |
| Suavizado LOO candidatos ½ / ¼ / 1/10 | V14 **diagnóstico**; elegido ¼ / ¼ / ⅛ (no ½ / ¼ / 1/10) |
| Contracción por fiabilidad | V12/V14 diagnóstico; **prohibida** en operativa fiel |

## Qué NO adoptar para la copia fiel

- Multiplicadores físicos fijos 0,62 / 0,55 / 0,85 como EQ principal.
- Suavizado regional LOO (½ oct subgrave) como curva operativa.
- `recommended = (diag+offset) × reliability` en 25–900 Hz.
- Perseguir +3,49 @ 515 Hz como verdad absoluta (pair-first crudo puede ir más alto; hold-out manda).

## Mejoras de bajos con sentido (sin romper fidelidad)

Prioridad si seguimos minando este sector:

1. **Ventana low real** (&lt;120 Hz): segmento ~60–760 ms (o alargar body) para cycles_score honestos.
2. **Usar `noise_profile`** pre-onset en PSD/SNR (ya está calculado).
3. **Energía relativa real** (−58/−68/−82) cuando haya potencia por evento, no solo proxy SNR.
4. **Activar rampa open 280–300** (quitar o suavizar el hard-cut del extract).
5. Opcional: split SNR/fase 600–900 más fino; broad/narrow solo como **diagnóstico** paralelo a DPSS.

## Conclusión

V4.1 es más cuidadoso en **resolución temporal de subgrave**, **ruido/hum musical**, y **no copiar dientes de fundamental**.  
Nosotros somos más fuertes en **estimación espectral (DPSS/F0)**, **agregación sin contracción ciega**, y **validación de copia**.  

La operativa actual ya cuenta la historia correcta en bajos (subgrave suave, cuerpo en 350–600). El gap vs V4.1 en 515 Hz es magnitud/forma local, no filosofía. El siguiente salto útil en 25–900 Hz es **ventana low + ruido pre-onset + energía relativa**, no más shrink ni multipliers.
