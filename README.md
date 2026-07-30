# copia-azul-rc-mooer

Repositorio organizado en tres módulos independientes con audio y nombres normalizados.

## Módulos

| Módulo | Rol |
|---|---|
| [`modules/emulate_azul`](modules/emulate_azul) | Emular el Bajo Azul desde el Café (transferencia Café→Azul, V10.2) |
| [`modules/rc_pedals`](modules/rc_pedals) | Medir/reconstruir respuestas de los pedales RC (bass / hybrid / guitar) |
| [`modules/mooer_eq`](modules/mooer_eq) | Modelo en PC del EQ del Mooer GE300 + optimización de presets |

## Audio normalizado

| Carpeta | Contenido |
|---|---|
| [`audio/cafe_vs_azul`](audio/cafe_vs_azul) | 16 pares Café/Azul (notas, acordes, cromática) |
| [`audio/rc_response`](audio/rc_response) | Pink + sweep 1–22 kHz, OFF y RC on |
| [`audio/azul_forced`](audio/azul_forced) | Pink + sweep con Azul forced (bass/hybrid/guitar) |

Convención de nombres: [`manifests/NAMING.md`](manifests/NAMING.md)  
Mapa old→new: [`manifests/rename_map.csv`](manifests/rename_map.csv)

## Inventarios

- [`manifests/cafe_vs_azul_pairs.csv`](manifests/cafe_vs_azul_pairs.csv)
- [`manifests/rc_response_inventory.csv`](manifests/rc_response_inventory.csv)
- [`manifests/azul_forced_inventory.csv`](manifests/azul_forced_inventory.csv)

## Relación entre módulos

```text
audio/cafe_vs_azul  ──►  emulate_azul   (curva Café→Azul)
audio/rc_response   ──►  rc_pedals      (curvas RC)
audio/azul_forced   ──►  emulate_azul   (futuro: Azul por pink/sweep)
rc_pedals curvas    ──►  mooer_eq       (presets GE300)
```

## Nota de portabilidad

Los scripts legacy aún pueden referenciar rutas `/mnt/data/...` de corridas anteriores. La reorganización normaliza estructura y audio; adaptar paths es trabajo siguiente.
