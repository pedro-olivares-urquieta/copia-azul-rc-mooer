# Mapa metodológico: informe V4.1 ultraprofundo ↔ nuestro pipeline

**Fecha:** 2026-07-31  
**Nuestro stack:** V10.2 → V11 → V12 → V13 → **V14**  
**Referencia:** informe metodológico ultraprofundo Café→Azul (V4.1, 912 pts, PSD Hann)

Regla de oro: **no adoptar como “mejora” algo que ya hacemos mejor**, ni reescribir la ciencia de `build_v10_2` de un golpe. Lo adoptado entra como post-proceso trazable (`improve_v12`…`v14`).

---

## 1. Qué intenta resolver (acuerdo total)

Ambos pipelines separan:

```text
diferencia observada = timbre estable + nivel + geometría + ejecución + grabación + error
```

y entregan **curva EQ** + **ganancia residual** independientes. Eso ya era nuestro contrato (V11 cierra la fuga de nivel dentro de Q(f); V12 neutraliza energía).

---

## 2. Tabla sección → estado

| §§ V4.1 | Tema | Estado | Nota corta |
|---|---|---|---|
| 2–4 | Material, inventario, decode mono | **TENEMOS** | Manifest + SHA + QC; float64 análisis (decode float32) |
| 5–6 | Onsets | **MEJOR NOSOTROS** | Mel-flux determinista bit-idéntico (`onsets.py`) |
| 7–8 | Matching / cromática DP | **TENEMOS / MEJOR** | DP monotónico con costo acústico, no solo orden equidistante |
| 9 | Segmentos attack/sustain/low | **MEJOR NOSOTROS** | 5 fases; V13 publica curvas; V14 mezcla regional tipo §29 |
| 10–11 | PSD | **MEJOR NOSOTROS** | Multitaper DPSS; ellos Hann homogéneo |
| 12–14 | Rejilla / broad–narrow | **PARCIAL** | Rejilla 4096; broad/narrow **no** (ajornado: no es el cuello) |
| 15 | F0 | **MEJOR NOSOTROS** | Refine ±3.5% cableado; V4.1 etiqueta sin refiner en núcleo |
| 17–19 | Ruido + SNR regional | **TENEMOS** | V12 |
| 20 | Energía relativa | **PARCIAL** | Solo `wenergy` armónico; no umbral regional completo |
| 21–23 | Ciclos / AAC / open 280–300 | **TENEMOS / PARCIAL** | Ciclos+AAC V12; soft open inerte (hard cut upstream) |
| 24–25 | Δ espectral − gain; pesos | **PARCIAL→V14** | Producto de pesos casi completo; falta `rel` explícito |
| 27–28 | Agregación pareja + Kish | **TENEMOS + V14** | Kish V12; **pair-first** curva diagnóstica V14 |
| 29–30 | Mezcla temporal + desacuerdo A/S | **ADOPTADO V14** | Tabla §29 + `attack_sustain_disagreement_db` |
| 32 | Heurística física 0.62/0.55/0.85 | **NO ADOPTAR** | Offsets estimados joint ≫ constantes fijas |
| 33–35 | Suavizado regional held-out | **ADOPTADO V14** | Candidatos + parsimonia 0.08 dB |
| 36 | Neutralidad energética | **TENEMOS** | V12 |
| 37–38 | Bootstrap / LOPO | **MEJOR NOSOTROS** | + LOFO/LOSO/LORO/LOEO |
| 39–42 | Red / fiabilidad geométrica / shrink | **ADOPTADO V14** | Rodillas recalibradas a N_eff≈1.26 |
| 44–45 | Gain non-open sustain | **ADOPTADO V14** | Estimador extra; no sustituye energy-neutral |
| 51–53 | Limitaciones / lectura | **ACUERDO** | 16 parejas; AAC; EQ estática; WAV DI sería el salto real |

---

## 3. Qué hacemos mejor (no regresar)

1. **DPSS** frente a Hann único.  
2. **F0 refinada en el fit**.  
3. **Offsets por cuerda/registro/fase estimados**, no ×0.62/0.55/0.85.  
4. **Matching acústico monotónico** + cromática con costo de nota.  
5. **Reproducibilidad bit-idéntica** + manifiestos.  
6. **Más CV** (familia, cuerda, registro, ejercicio, pareja).  
7. **Cierre del bucle gain↔curva** (V11) — V4.1 resta RMS por evento pero no itera Q(f).  
8. **5 fases** + curvas publicadas (V13), no solo 3 ventanas.

---

## 4. Qué se adoptó de este informe

| Idea V4.1 | Dónde | Entrega |
|---|---|---|
| Kish N_eff | V12 | `effective_pairs_kish` |
| SNR regional, ciclos, AAC, red | V12 | `PESOS_EVIDENCIA_V12.csv` |
| Neutralidad energética | V12 | `energy_neutral_db`, gain ≈ −12.04 dB |
| Curvas ataque/sustain | V13 | `CURVAS_POR_FASE_V13.csv` |
| LOPO + headroom | V13 | `VALIDACION_LOPO_V13.csv` |
| **Agregación pair-first** | **V14** | `CURVA_PAIR_FIRST_V14.csv` |
| **Desacuerdo ataque–sustain** | **V14** | columna + `phase_score` |
| **Suavizado regional held-out** | **V14** | `SUAVIZADO_REGIONAL_V14.csv` |
| **Mezcla fase×frecuencia §29** | **V14** | fit diagnóstico `CURVAS_DENSAS_V14_FIT.csv` |
| **Fiabilidad geométrica recalibrada** | **V14** | `FIABILIDAD_V14.csv` |
| **Gain non-open sustain** | **V14** | `GAIN_NO_OPEN_SUSTAIN_V14.json` |

---

## 5. Qué no se adopta (y por qué)

| Idea | Motivo |
|---|---|
| Multiplicadores físicos fijos | Regresión frente a offsets estimados |
| Bajar a 912 puntos | Densidad no es el límite; N_eff≈1.26 sí |
| Broad/narrow blend | Reescritura espectral; beneficio dudoso con DPSS+parciales |
| Soft open 280–300 sin re-extract | Inerte mientras el hard cut viva en `build_v10_2` |
| Tratar V4.1 presencia (+6 dB) como verdad | Misma evidencia débil; discrepancias de método |

---

## 6. Lectura operativa (resultado V14)

| Estimador de gain | Valor |
|---|---|
| V12 energy-neutral | −12.04 dB |
| V14 pair-first neutral | −11.84 dB |
| V14 non-open sustain (mediana) | −11.82 dB |
| V4.1 residual (informe) | −11.94 dB |
| RMS audio activo (V13) | −12.14 dB |

**Gain ≈ −12 dB** sigue siendo la magnitud más sólida del proyecto.

### Hallazgo crítico sobre la presencia (2–6 kHz)

Al agregar **pair-first** (como V4.1), la curva neutra se acerca a las magnitudes del informe en medios (~515 Hz: +3.1 vs +3.5 dB) y **sube aún más** en presencia (p. ej. 2630 Hz: +11.7 vs V4.1 +6.6 vs V12 +2.3).

Pero el **MAE held-out por pareja** en esa misma banda es ~**11 dB**. Es decir: la magnitud “tipo V4.1” **no generaliza** de 15 parejas a la 16ª. Eso no prueba que V4.1 esté mal ni que V12 esté bien; prueba que **con 16 parejas la forma fina de presencia es inidentificable**, y que cambiar el agregador mueve el pico varios dB.

Por eso:

- `pair_first_*` / `energy_neutral_db` V14 = **diagnóstico** de sensibilidad al agregador.
- `recommended_db` V14 (contracción por fiabilidad) = implementación conservadora.
- **No regenerar presets MOOER Azul+RC** apoyados en +15.5 dB @ 3637 Hz hasta tener más evidencia (WAV/DI / más sesiones).

### Suavizado regional seleccionado (held-out + parsimonia 0.08 dB)

| Región | Ancho (octavas) | MAE held-out |
|---|---:|---:|
| Subgrave | 1/4 | ~2.0 dB |
| Grave | 1/4 | ~2.6 dB |
| Medio bajo | 1/8 | ~5.9 dB |
| Medio / presencia / agudo | 1/8 | ~10–12 dB |
| Aire | 1/2 | ~12.4 dB |

(Comparable en espíritu a V4.1 §34; aquí el held-out revela que medios-altos no soportan anchos finos con valor predictivo.)

- **Próximo salto real** (acuerdo con §53): WAV/DI, más sesiones, validación auditiva ciega — no más puntos en la tabla.

---

## 7. Cómo reproducir V14

```bash
AZUL_OUT_DIR=modules/emulate_azul/_runs/<run>/results \
AZUL_RENDERS_DIR=modules/emulate_azul/_runs/<run>/renders \
python3 modules/emulate_azul/code/improve_v14.py
```
