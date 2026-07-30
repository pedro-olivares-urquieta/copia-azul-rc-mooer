# Convención de nombres de audio

Formato general:

```text
{signal_or_instrument}__{role}[__{detail}].m4a
```

Separador de campos: `__` (doble guion bajo).  
Todo en minúsculas ASCII, sin espacios ni acentos.

## `audio/cafe_vs_azul`

```text
{instrument}__note_{note}__{position}.m4a
{instrument}__chord_{chord}.m4a
{instrument}__chromatic_{root}__{range}.m4a
```

| Campo | Valores |
|---|---|
| `instrument` | `cafe`, `azul` |
| `note` | `a`, `b`, `c`, `d`, `e`, `g` |
| `position` | `open`, `fret_12`, `fret_24` |
| `chord` | `am7`, `cmaj7` |
| `range` | `frets_1_25` |

Ejemplos:

- `cafe__note_e__open.m4a`
- `azul__note_c__fret_24.m4a`
- `cafe__chord_am7.m4a`
- `azul__chromatic_c__frets_1_25.m4a`

## `audio/rc_response`

```text
{signal}__off.m4a
{signal}__rc_{profile}.m4a
```

| Campo | Valores |
|---|---|
| `signal` | `pink`, `sweep_1_22k` |
| `profile` | `bass`, `hybrid`, `guitar` |

## `audio/azul_forced`

```text
{signal}__azul_{profile}.m4a
```

Misma `signal` / `profile` que arriba.  
Nota: el archivo fuente `Pink azul rc guitar forced.m4a` se normalizó a `pink__azul_guitar.m4a` (el token `rc` era inconsistente).
