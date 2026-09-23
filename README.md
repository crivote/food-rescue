# Food Rescue — Reto "¿Cuánta comida puedes salvar?"

Solución para el reto **AI for Action** (<https://aiforaction.tech/comida>): asignar
comida perecedera de supermercados a bancos de alimentos en una tarde, contra un
simulador de eventos discretos.

La entrega es un **motor de asignación determinista** (`solver_match_crit.py`): un
emparejamiento de coste mínimo que se re-ejecuta en cada tic del simulador (5
minutos), con tres reglas de priorización calibradas empíricamente. No usa ningún
modelo externo ni dependencia fuera de la biblioteca estándar de Python.

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
2. El peso de cada viaje combina **cuatro** factores:

```
peso = (comidas / duración)                       ← eficiencia del viaje
     × (1 + BETA / n_cap)                         ← criticidad (exclusividad)
     × (1 + DESIERTO · m)                         ← bono de lejanía
     × (1 − NEAR_K · (NEAR_KM − d)/NEAR_KM)       ← malus de cercanía
```

- **Criticidad** (`n_cap`): número de voluntarios capaces de rescatar esa recogida
  *en su ventana completa*, recalculado en cada tic. Una recogida que solo un
  voluntario puede alcanzar recibe más peso. Es la regla que más aporta.
- **Desierto**: bono para recogidas lejanas a su centro más cercano (> 5 km), el
  doble en el primer viaje de un voluntario (coste de oportunidad de ida desde
  casa).
- **Cercanía**: malus para recogidas pegadas a su centro (< 4 km), que son viajes
  baratos y conviene no consumir mientras quede tiempo.

Los parámetros (`BETA=1.4`, `DESIERTO=0.2`, `DESIERTO_KM=5.0`, `NEAR_K=0.5`,
`NEAR_KM=4.0`) son **fijos y globales**: se verificó que hacerlos depender de las
características de cada escenario no aporta mejora, y que su valor óptimo es el
mismo en los cuatro cuartiles de dificultad.

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
ai-for-good-72h-harness/        ← simulador del reto (MIT, ajeno)
    comida/simulate.py          ← motor del simulador
    comida/generar_escenario.py ← generador determinista de escenarios
    comida/baseline_greedy.py   ← greedy de referencia
    comida/scenarios/sample_01.json
firma_global.py                 ← parámetros topológicos de un escenario
estratifica_cuartiles.py        ← estratificación por cuartiles de dificultad
bench_alcanzable.py             ← umbral máximo simplificado
techo_realista.py               ← umbral máximo por grafo de itinerarios (LP)
optimo_exacto.py                ← óptimo entero de un escenario (CP-SAT)
valida_beta_14.py               ← validación por pares del parámetro BETA
```

## Licencia

El motor y los scripts de validación de este repositorio están bajo la licencia
**MIT** (ver `LICENSE`). El simulador (`ai-for-good-72h-harness/`) es ajeno y se
distribuye bajo su propia licencia MIT (ver `ai-for-good-72h-harness/LICENSE`).
