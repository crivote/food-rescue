# Food Rescue — Reto "¿Cuánta comida puedes salvar?"

Solución para el reto **AI for Action** (<https://aiforaction.tech/comida>): asignar
comida perecedera de supermercados a bancos de alimentos en una tarde, contra un
simulador de eventos discretos.

La entrega es un **motor de asignación determinista** (`solver_match_crit.py`): un
emparejamiento de coste mínimo que se re-ejecuta en cada tic del simulador (5
minutos), con tres reglas de priorización calibradas empíricamente. No usa ningún
modelo externo ni dependencia fuera de la biblioteca estándar de Python. Existe,
además, una capa de IA **opcional** (aprendizaje por imitación) medida pero no
integrada, documentada en [`docs/AI_METHODS.md`](docs/AI_METHODS.md).

---

## TL;DR — qué es real, qué es simulado y qué fuentes usamos

**Qué funciona de verdad.** El motor (`solver_match_crit.py`) es código real,
determinista y autocontenido (solo biblioteca estándar de Python). No es un plan
precalculado ni un script que devuelva valores fijos: en cada tic del simulador
recibe el estado completo, resuelve un emparejamiento de coste mínimo y devuelve
las asignaciones de ese instante. Es reproducible — la misma entrada produce
siempre la misma salida — y nada está inventado ni ajustado a mano por escenario.

**Qué está simulado.** Los *resultados* (el porcentaje de comida salvada) se miden
sobre el simulador de eventos discretos del reto, no sobre entregas reales de
comida. El escenario publicado (`sample_01`) y los 2000 escenarios de validación
provienen del generador oficial del reto (`generar_escenario.py`, determinista y
con semilla fija). El 55.4% del escenario publicado es la salida real de ese
simulador ejecutando nuestro motor, reproducible con el comando de la sección
*Ejecución*.

**Qué fuentes usamos.** Ninguna teórica — ni papers ni fórmulas tomadas de la
literatura. Toda la calibración (los tres factores del peso y sus valores) es
**pura empiria**: cada parámetro se fijó midiendo su efecto sobre el simulador y
descartando los que no aportaban. `docs/METODOLOGIA.md` registra qué se probó,
qué se refutó y con qué evidencia.

**La salvedad de los datos.** Las fuentes abiertas del reto (OpenStreetMap,
FAO, Eurostat, ReFED, FESBAL, portales municipales) sirven para *dimensionar* el
problema, no para *decidir* en tiempo real: no existe hoy una API donde
supermercados, voluntarios y centros publiquen su estado en vivo. El motor se
alimenta del generador determinista del reto; la capa de datos es intercambiable
solo si existiera ese feed, que es el punto de partida de la visión de producto
de la sección siguiente.

---

## El problema

- **11 voluntarios**, cada uno con posición inicial (su casa), una ventana de 2 h,
  una velocidad (9–15 km/h) y una capacidad de carga (15–30 raciones).
- **43 recogidas** de comida, cada una con posición, número de raciones y hora de
  caducidad.
- **6 bancos de alimentos** (centros) con hora de cierre.
- El simulador avanza en tics de 5 minutos y, en cada tic, espera una lista de
  asignaciones `{voluntario, recogida, centro}`.

**Cada decisión es un solo viaje** (`voluntario → recogida → centro`). No se
encadenan dos recogidas en un viaje. El voluntario queda libre de nuevo tras
entregar en el centro y puede re-despacharse mientras le quede tiempo. Este
*re-despacho* es el corazón del problema.

Dos voluntarios cancelan a mitad de la tarde (a las 19:40 en el escenario
publicado), lo que obliga a **replanificar en caliente**, no a ejecutar un plan
calculado al inicio.

### Métrica

```
porcentaje_salvado   → manda
comidas_por_hora     → desempata
```

## Resultados

Sobre el escenario publicado (`sample_01`, 775 raciones):

| Motor | % salvado |
|---|---|
| Greedy de referencia (el del reto) | 42.1% |
| Emparejamiento comidas/minuto (referencia de la documentación) | ~53.4% |
| **Este motor** | **55.4%** |

En el conjunto de validación (2000 escenarios fuera de muestra, estratificados
por dificultad), el motor supera a ambas referencias en los **cuatro cuartiles**:

| Cuartil | Greedy | Matcher base | **Motor** | Mejora vs base |
|---|---|---|---|---|
| Q1 (fácil) | 51.7% | 58.1% | **62.8%** | +4.6 |
| Q2 | 48.0% | 54.9% | **58.9%** | +4.1 |
| Q3 | 45.0% | 51.5% | **54.9%** | +3.4 |
| Q4 (difícil) | 41.5% | 46.6% | **49.9%** | +3.4 |

El detalle completo de la validación (parámetros topológicos, índice de
dificultad, umbrales mínimo y máximo, y la justificación empírica de cada
parámetro) está en [`docs/METODOLOGIA.md`](docs/METODOLOGIA.md).

## Cómo funciona el motor

`decidir(estado)` recibe el estado completo del simulador en cada tic y devuelve
las asignaciones de ese tic. En cada llamada:

1. **Emparejamiento de coste mínimo** (min-cost flow) entre voluntarios libres y
   recogidas pendientes, optimizando el peso de cada viaje candidato.
2. El peso de cada viaje combina **tres reglas operativas** (todas en forma de
   factor multiplicativo, calculadas sobre la base `comidas/duración`):

```
peso = (comidas / duración)                       ← eficiencia del viaje (base)
     × (1 + BETA / n_cap)                         ← criticidad (exclusividad)
     × (1 + DESIERTO · m)                         ← bono de lejanía (m ∈ {1,2})
     × (1 − NEAR_K · (NEAR_KM − d)/NEAR_KM)       ← malus de cercanía
```

- **Criticidad** (`n_cap`): número de voluntarios capaces de rescatar esa recogida
  *en su ventana completa*, recalculado en cada tic. Una recogida que solo un
  voluntario puede alcanzar recibe más peso. Es la regla que más aporta.
- **Desierto**: bono para recogidas lejanas a su centro más cercano (> 5 km),
  con `m=2` si el voluntario está en su posición de partida (primer viaje, con
  coste de oportunidad de ida desde casa) y `m=1` en los re-despachos. El bonus
  es continuo: en un escenario sin recogidas lejanas vale exactamente 1 (no
  añade ruido). El factor `m` es parte de esta regla, no un cuarto factor
  independiente.
- **Cercanía**: malus para recogidas pegadas a su centro (< 4 km), que son viajes
  baratos y conviene no consumir mientras quede tiempo. Es el espejo simétrico
  del desierto.

Los parámetros (`BETA=1.4`, `DESIERTO=0.2`, `DESIERTO_KM=5.0`, `NEAR_K=0.5`,
`NEAR_KM=4.0`) son **fijos y globales**: se verificó que hacerlos depender de las
características de cada escenario no aporta mejora, y que su valor óptimo es el
mismo en los cuatro cuartiles de dificultad.

## El método de IA (medido, capa opcional)

El motor de arriba es un matcher *local*: en cada tic optimiza el presente sin
ver el coste de oportunidad futuro (qué recogida sacrifica al consumir un
voluntario capaz). Su límite no está en los pesos —se verificó que modularlos no
aporta— sino en esa **miopía secuencial**. El método para atacarla fue un
**aprendizaje por imitación** (behavioral cloning) del solucionador exacto:

- **Profesor (offline).** `optimo_exacto.py` resuelve cada escenario a óptimo
  entero con CP-SAT. Es el oráculo que conoce la asignación global correcta.
- **Alumno (online, determinista).** Un modelo de puntuación (LightGBM,
  LambdaRank) aprende, a partir de los planes óptimos, a dar a cada arista
  `(voluntario, recogida)` el peso que habría llevado al profesor a elegirla.
  Sustituye la **fórmula artesanal del peso**, manteniendo intacta la capa de
  emparejamiento (`min-cost flow`) que ya garantiza factibilidad y determinismo.
- **Por qué es determinista.** El profesor corre offline (da igual cuál de sus
  soluciones óptimas empatadas devuelva); el alumno tiene pesos fijos, así que
  toda la cadena online produce siempre la misma salida.

**Resultado (medido, fuera de muestra, 1200 semillas estratificadas).** El
scorer aprendido **bate al motor determinista en los cuatro cuartiles de
dificultad**:

| Cuartil | Motor | Scorer | Δ |
|---|---|---|---|
| Q1 (fácil) | 62.69% | 63.30% | +0.61 |
| Q2 | 59.19% | 60.01% | +0.82 |
| Q3 | 54.74% | 55.46% | +0.72 |
| Q4 (difícil) | 49.38% | 50.20% | +0.82 |
| **Total** | **56.50%** | **57.24%** | **+0.74** |

Es una mejora **real y estable** (+0.74 pts, gana en el 57% de los casos), pero
**modesta**: el margen in-sample (+2.2 pts) se reduce fuera de muestra por
overfitting parcial. Las variantes para ampliarla (features globales, labels
ponderados) no aportaron; el límite es estructural — el profesor optimiza un
plan global, y sus etiquetas por tic solo codifican decisiones locales. **Esta
capa es opcional y no está integrada en el motor publicado**: los resultados de
la sección anterior corresponden al motor determinista ya consolidado.

El detalle técnico está en [`docs/AI_METHODS.md`](docs/AI_METHODS.md) y
[`docs/METODOLOGIA.md`](docs/METODOLOGIA.md), sección 7.

> **Reproducir los números del scorer.** Las cifras de la tabla anterior
> (Q1=+0.61 … Q4=+0.82) proceden de un modelo entrenado sobre 600 escenarios
> OPTIMAL (semillas 20300–20899), validado contra 1200 escenarios fuera de
> muestra (5001–6200). El modelo (2.7 MB) y los planes CP-SAT (665 KB) son
> artefactos regenerables, no versionados: ejecuta `bash ml/build_scorer.sh`
> (~2 h de CPU en 4 cores) para obtenerlos desde cero. Los scripts están
> diseñados para correr en CPU y son deterministas (semillas explícitas).
> Mientras el modelo no exista, `ml/solver_scorer.py` cae al fallback `[]`
> (silencioso); el orquestador debe comprobar la disponibilidad del modelo.

## Ejecución

Requisitos: Python 3.10+ (solo biblioteca estándar para el motor; el solucionador
exacto de referencia usa `ortools`).

```bash
# correr el motor contra el escenario publicado
python3 ai-for-good-72h-harness/comida/simulate.py \
    --scenario ai-for-good-72h-harness/comida/scenarios/sample_01.json \
    --solver solver_match_crit.py
```

Devuelve (55.4% en el escenario publicado):

```json
{
  "metrica_principal": "porcentaje_salvado",
  "desempate": "comidas_por_hora",
  "porcentaje_salvado": 55.4,
  "comidas_rescatadas": 429,
  "comidas_totales": 775
}
```

## Estructura

```
solver_match_crit.py            ← el motor (la entrega)
solver_match.py                 ← matcher base (referencia sin heurísticas)
docs/METODOLOGIA.md             ← validación completa: metodología y evidencia
docs/AI_METHODS.md              ← método de IA: scorer por imitación (técnico)
ai-for-good-72h-harness/        ← simulador del reto (MIT, ajeno)
    comida/simulate.py          ← motor del simulador
    comida/generar_escenario.py ← generador determinista de escenarios
    comida/baseline_greedy.py   ← greedy de referencia
    comida/scenarios/sample_01.json
firma_global.py                 ← parámetros topológicos de un escenario
estratifica_cuartiles.py        ← estratificación por cuartiles de dificultad
bench_alcanzable.py             ← umbral máximo simplificado (techo por ítem)
optimo_exacto.py                ← óptimo entero de un escenario (CP-SAT)
valida_beta_14.py               ← validación por pares del parámetro BETA
ml/                             ← capa de IA (aprendizaje por imitación)
    etiquetar_cpsat.py          ← genera el material de entrenamiento del scorer
    scorer_features.py          ← features del scorer (fuente única)
    entrenar_variantes.py       ← entrena el scorer (LightGBM LambdaRank)
    solver_scorer.py            ← motor online con el scorer aprendido
    bench_estratificado.py      ← motor vs scorer fuera de muestra, por cuartiles
explicar_decision.py            ← traduce una decisión a lenguaje natural (LLM)
ux/index.html                   ← prototipo de app de voluntario (sin build)
```

## Visión de producto — del simulador al sistema real

Este repositorio es el **motor de decisión**, no el sistema completo. El paso a
producción pasa por una pieza que hoy no existe y que habría que diseñar: una
**API abierta** y una arquitectura cloud donde los tres tipos de actor publican y
consumen su estado en tiempo real, **sin compromiso**, bien mediante una app
interactiva o mediante integraciones automatizadas con sus sistemas de
información.

- **Oferentes de excedente** — restaurantes, hoteles, comedores de universidades
  y colegios, intermediarios de alimentación, hipermercados, supermercados.
  Publican *qué* les sobra, *cuándo* caduca y *dónde* está.
- **Voluntarios** — colaboran recogiendo y transportando. Para sostener la
  participación se propone un sistema **gamificado de puntos y recompensas**
  (virtuales y, si se logra patrocinio de una fundación o entidad con interés en
  posicionar su imagen corporativa en recuperación de alimentos, reales).
- **Puntos de recogida y almacenamiento del tercer sector** — bancos de
  alimentos — con capacidad y horario en vivo.

El motor de este repositorio es directamente reutilizable como el núcleo de
decisión de ese sistema: la interfaz `decidir(estado)` no cambia; solo cambia
quién produce el `estado` (el simulador, o la API en tiempo real del sistema).

Como muestra del salto a producto, `ux/index.html` es un prototipo estático de
la app del voluntario (HTML + CSS + JS vanilla, sin build) que reproduce el
flujo *misión → aceptar → recoger → entregar → recompensa*, con gamificación de
puntos y la explicación de por qué se asignó cada recogida. Esa explicación no
está hardcodeada: `explicar_decision.py` la genera traduciendo el contexto de
decisión del motor a lenguaje natural con un LLM barato (mecanismo descrito en
[`docs/AI_METHODS.md`](docs/AI_METHODS.md), §9).

## Licencia

El motor y los scripts de validación de este repositorio están bajo la licencia
**MIT** (ver `LICENSE`). El simulador (`ai-for-good-72h-harness/`) es ajeno y se
distribuye bajo su propia licencia MIT (ver `ai-for-good-72h-harness/LICENSE`).
