# Análisis: presencia / brillo / aire (V4.1) vs nosotros

## Veredicto corto sobre 15–18 kHz

**Sí, nos pasamos.** La operativa V19 dejaba ~**+3.7…+4.5 dB** de 8 a 18 kHz porque `presence_scale` multiplica todo ≥500 Hz.  
V4.1 trata 10–18 kHz como **diagnóstico** y contrae hacia 0 (AAC prior 0.72→0.08 + fiabilidad).  
V20 corrige solo el aire, sin suavizar presencia 2.5–6 kHz.

| Hz | V19 (antes) | Política V4.1 |
|---:|---:|---|
| 6 kHz | ~+4.1 | presencia/brillo, defendible con cautela |
| 10 kHz | ~+4.5 | borde diagnóstico |
| 15 kHz | ~+3.8 | prior AAC ~0.20 → casi no recomendar |
| 18 kHz | ~+3.7 | prior AAC ~0.08 → ~0 dB |

## División que adoptamos conceptualmente

| Región | Rango | Nosotros |
|---|---|---|
| Presencia | 2.5–6 kHz | Operativa (V19 robusta); métrica render |
| Brillo | 6–10 kHz | Parcial; AAC prior en pesos; no shrink ciego |
| Aire | 10–18 kHz | **Diagnóstico** → V20 taper hacia 0 |

## Qué hacemos mejor

1. **DPSS** vs Hann único  
2. **F0 refine** cableado  
3. **Matching acústico** (no solo orden)  
4. **Offsets estimados** (no ×0.62/0.55/0.85)  
5. **Métrica de copia** Café+EQ vs Azul (hold-out)  
6. **No smooth** ni `EQ×reliability` en 0.5–8 kHz (evita aplanar presencia real)

## Qué ya teníamos del informe (bien)

- Mezcla fase §29: 2.5–6k 40/60, 6–10k 64/36, >10k 80/20 (`PHASE_MIX` V14)  
- SNR regional 10 / 12 / 14 dB  
- Prior AAC idéntico en observación  
- Open >300 Hz fuera de presencia/brillo/aire  
- Separación gain vs timbre  

## Qué faltaba (y causaba el exceso en 15–18 kHz)

1. **`presence_scale` global ≥500 Hz** arrastraba el aire  
2. No había **política explícita de aire** en la curva operativa (solo en pesos)  
3. V4.1 además suaviza ½ oct y contrae por fiabilidad — eso **no** lo queremos en presencia, pero **sí** un taper hacia 0 en aire

## Qué NO adoptamos

- Suavizado regional 1/6–1/2 oct como entregable  
- Contracción `EQ × reliability` en medios/presencia  
- Asumir que +6 dB @ 2.6/4.1 kHz del informe es verdad absoluta  

## Lectura práctica

- **2.5–6 kHz:** identidad Azul; V19 ataca desacuerdo entre parejas  
- **6–10 kHz:** brillo/ataque; confianza moderada; AAC empieza a pesar  
- **10–18 kHz:** textura/AAC; no clonar; volver a ~0 dB en la EQ operativa  
