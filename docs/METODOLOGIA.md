# Validación y mejora del motor de distribución

> Documento consolidado. Describe cómo se valida el motor de asignación, qué
> límites (mínimos y máximos) se usan como referencia, y qué mejoras se
> incorporaron tras medirlas empíricamente. El vocabulario es deliberadamente
> neutro: se habla de "motor", "asignación", "recogidas", "voluntarios" y
> "centros". El motor publicado (secciones 1–6) es puramente determinista
> (reglas + optimización combinatoria); la sección 7 describe un plan de
> aprendizaje automático *en curso*, todavía no integrado en el motor.

---

## 1. Contexto de validación

Probar el motor contra un único escenario no es significativo: un solo caso
favorece el sobreajuste y no dice nada de cómo se comportará el motor en
situaciones distintas. Por eso toda la evaluación se hace sobre **conjuntos de
escenarios generados de forma reproducible** (semilla fija, mismo generador que
el reto) y se estratifica por dificultad estructural.

### 1.1 Conjunto de escenarios

Se generan **2000 escenarios aleatorios** (semillas 5001–7000) con el generador
público del reto. Cada escenario es una ciudad sintética con 43 recogidas de
comida, 11 voluntarios y 6 centros, con tiempos, velocidades y capacidades
sorteados. La dificultad varía entre escenarios por pura geometría y
distribución de caducidades.

Sobre cada escenario se calculan **parámetros topológicos** independientes del
motor (es decir, propiedades de la disposición de los nodos, no del resultado
de ninguna regla):

| Parámetro | Qué mide |
|---|---|
| `alcanzable_pct` | % de comida que *algún* voluntario podría salvar desde su posición inicial, ignorando que no puede hacer todos los viajes. Mide la comida físicamente irrecuperable por tiempo/distancia/capacidad. |
| `comida_grande` | % de comida en recogidas de más de 25 raciones (solo caben en voluntarios de capacidad 30). |
| `comida_grande_por_cap30` | Cuello de botella de capacidad: comida grande dividida entre el nº de voluntarios cap-30. |
| `d_rec_centro_media` / `_p90` | Distancia media (y percentil 90) de cada recogida a su centro más cercano. La cola alta es el "desierto" (recogidas lejanas). |
| `d_vol_rec_media` | Distancia media de cada voluntario a su recogida más cercana. |
| `dispersion_rec` / `_vol` | Dispersión media entre vecinos más próximos (recogidas y voluntarios): agrupamiento espacial. |
| `asimetria` | Distancia entre el centro de masa de las recogidas y el de los centros. |
| `frac_caduca_temprano` | % de recogidas que caducan antes de 55 min desde la apertura. |

El análisis de estos parámetros permite **ordenar los escenarios en cuatro
cuartiles**, del más fácil al más difícil, según la comida irrecuperable y los
cuellos de botella de tiempo y espacio.

### 1.2 Índice de dificultad

El índice combina las tres magnitudes que más correlacionan con la dificultad
de cada escenario (z-score sobre la muestra):

```
dificultad = −z(alcanzable_pct) + z(comida_grande_por_cap30) + 0.5·z(d_rec_centro_media)
```

- `alcanzable_pct` alto ⇒ escenario fácil ⇒ signo **negativo**.
- `comida_grande_por_cap30` alto ⇒ cuello de botella de capacidad ⇒ difícil.
- `d_rec_centro_media` alto ⇒ mucho desierto ⇒ difícil (peso a la mitad).

Con este índice se parte la muestra en **cuatro cuartiles de igual tamaño** (500
escenarios cada uno), de Q1 (fácil) a Q4 (difícil). La estratificación es **por
estructura, no por resultado del motor**, lo que evita sesgo: se mide cómo se
comporta el motor en los escenarios que un evaluador exigente elegiría, sin
"aprender" del propio resultado.

---

## 2. Umbrales mínimos (líneas base)

Sobre los 2000 escenarios se ejecutan dos motores de referencia:

1. **Greedy del reto** (`baseline_greedy.py`): el repartidor voraz que
   proporciona la organización como referencia.
2. **Matcher base** (`solver_match.py`): asignación por emparejamiento de coste
   mínimo que optimiza directamente comidas/minuto por viaje, sin ninguna
   heurística adicional. Es la referencia "culta" del problema (emparejamiento
   bipartito por ronda).

La media de % de comida recuperada, global y por cuartil, es la **línea base**
contra la que se mide cualquier mejora:

| Cuartil | Greedy | Matcher base | Motor final | Mejora vs base |
|---|---|---|---|---|
| Q1 (fácil) | 51.7% | 58.1% | **62.8%** | +4.6 |
| Q2 | 48.0% | 54.9% | **58.9%** | +4.1 |
| Q3 | 45.0% | 51.5% | **54.9%** | +3.4 |
| **Q4 (difícil)** | 41.5% | 46.6% | **49.9%** | +3.4 |

*(Motor final = matcher base + las mejoras de la sección 4. La columna "mejora
vs base" es la ventaja real sobre la referencia culta, no sobre el greedy.)*

Nota de honestidad: no se ha conseguido reproducir exactamente el valor que la
documentación cita para el emparejamiento comidas/minuto (~53.4%), pero el
matcher base se queda cerca (51–58% según cuartil) y sirve como referencia
interna consistente.

---

## 3. Umbral máximo (techo de mejora)

Para no invertir esfuerzo en un problema ya resuelto, hace falta también un
**umbral superior**: cuánto se puede llegar a recuperar en cada escenario. El
problema es NP-difícil, así que no se puede resolver de forma óptima en todos
los escenarios con los medios disponibles. Esta sección documenta **el proceso**
que llevó del cálculo por estimación al techo real, con sus correcciones y los
caminos descartados.

### 3.1 Estimación simplificada (techo por ítem)

Primera cota: solo cuenta la comida **imposible** de salvar por los requisitos
de tiempo, distancia y capacidad de cada voluntario, ignorando la contención
(que un mismo voluntario no puede hacer todos los viajes). Es un límite superior
**muy holgado**:

- Media global: **~96%** (en el escenario publicado, solo 1 recogida de 43 es
  irrecuperable).

### 3.2 Estimación por relajación lineal (descartada tras corregir)

Segundo intento, más apretado: un **grafo de itinerarios** por voluntario
(secuencias `casa → recogida → centro → …`), con tiempos redondeados al tick
(hacia arriba, conservador) y respetando ventanas, capacidad y la regla de que
el primer viaje sale de casa y los siguientes de un centro. Se resuelve como un
problema de flujo/cubrimiento **relajando la integralidad** (se permite "partir"
una recogida entre dos viajes, físicamente imposible), lo que por diseño sitúa
la cota **por encima** del óptimo real.

**Proceso de depuración.** Esta cota pasó por **dos bugs** de modelado, que
empujaban en direcciones opuestas y se compensaban, por lo que el resultado no
parecía absurdo y pasó desapercibido:

1. **Teleport de origen.** Se asumía que cada viaje "desde centro" salía del
   centro **más cercano a la siguiente recogida**; el harness real fija al
   voluntario en el centro donde terminó el viaje anterior. Este defecto
   **inflaba** la cota (hasta 71.1% en el escenario publicado).
2. **`SetCoefficient` que no acumula.** Un viaje que sale y llega al *mismo*
   centro recibía coeficiente +1 y luego −1 sobre la misma variable; el segundo
   **sobrescribía** al primero, dejando la restricción más estricta de lo debido
   y la cota **por debajo** del óptimo (imposible en una relajación). Medido
   pareado en 40 escenarios: infravaloraba en 40/40 (media −2.67 pts).

Corregidos ambos, la jerarquía se restableció (`cota_LP ≥ óptimo_entero`), pero
la cota quedó **demasiado holgada para aportar** (media global 65.1% frente a
~62% el óptimo real, y una dispersión de ~8 pts entre cuartiles). La tabla de
"margen ~20 pts" que esta cota sugería era engañosa: el margen real es ~6 pts
(ver 3.3). Por eso la estimación lineal se **retira**: no es un límite útil y
confunde más de lo que aclara.

### 3.3 El techo real: solucionador exacto en batch

La única forma de obtener el techo **exacto** de un escenario es eliminar la
integralidad relajada y resolver el problema entero con CP-SAT (`optimo_exacto.py`).
Es NP-difícil, pero **para un escenario concreto es resoluble** y rápido:

| Magnitud (run batch) | Valor |
|---|---|
| Escenarios resueltos | 600 (semillas 20300–20899) |
| Alcanzaron `OPTIMAL` | **572 (95.3%)** |
| `FEASIBLE` (subóptimo, sin probar optimalidad) | 28 (4.7%) |
| Timeouts | 0 |
| Tiempo por escenario | media ~22.8 s, **mediana ~12 s** |

Con un techo exacto a ~12 s de mediana, no hace falta ninguna estimación: **el
margen se mide directamente, solo sobre las semillas donde el solver alcanzó
`OPTIMAL`**, sin extrapolar a semillas arbitrarias.

| Magnitud (escenario publicado, `sample_01`) | Valor |
|---|---|
| Motor final | **55.4%** (429 raciones) |
| Óptimo entero sin cancelaciones (origen exacto) | **64.6%** (501/775) |
| **Óptimo entero real** (con cancelaciones) | **61.8%** (479/775) |
| Plan "sin cancelaciones" ejecutado a ciegas en el harness | 54.8% (425/775) |
| Margen capturable real | **+6.4 pts** |

**Lectura de los dos óptimos.** El óptimo *sin* cancelaciones (64.6%) asume que
los 11 voluntarios trabajan toda su ventana. El óptimo *con* cancelaciones
(61.8%) es el número real: incorpora que v02 y v07 se caen a las 19:40. La
diferencia entre ambos (2.8 pts) es el coste estructural de perder dos
voluntarios. El dato de que un plan calculado *sin* saber de las cancelaciones y
ejecutado a ciegas rinde solo 54.8% (por debajo del propio motor, 55.4%)
confirma que **la incertidumbre de las cancelaciones es el factor que obliga a
replanificar en caliente**, no un plan único al inicio.

**Conclusión del umbral máximo:** el motor final (55.4%) está a **+6.4 puntos**
del óptimo alcanzable real (61.8%) en el escenario publicado. Hay margen real de
mejora, finito y medible — y se reporta **solo sobre la muestra de soluciones
óptimas**, no como una extrapolación.

### 3.4 Regresión del techo (explorada y descartada por error alto)

Con 572 semillas `OPTIMAL` y sus parámetros estructurales (sección 1.1), se
planteó aprender una **función escalar** `estructura → techo óptimo`, para
estimar el margen de *cualquier* semilla sin ejecutar el solver. Es una idea
mucho más sencilla que el scorer (una regresión, no una política), y la señal
existe: `alcanzable_pct` correlaciona +0.64 con el techo, `comida_grande_por_cap30`
−0.59 y `d_rec_centro_media` −0.42.

Sin embargo, el **error de predicción es demasiado alto** para resultar útil:

| Modelo lineal | RMSE fuera de muestra |
|---|---|
| Solo `alcanzable_pct` | 6.6 pts |
| + cuello de botella de capacidad | 6.3 pts |
| + distancia (3 features) | 5.6 pts |
| 6 features | **5.5 pts** |

Con un techo que oscila entre ~40% y ~85%, un error de ±5.5 pts no distingue
entre "mucho margen" y "poco margen" con la resolución necesaria, y no hay un
caso de uso que lo justifique: el techo es una cifra **diagnóstica** (no la
consume el motor para decidir), y ya se obtiene con exactitud a ~12 s del
solver. La regresión se **descarta por falta de valor**, no por inviabilidad.

---

## 4. Mejoras del algoritmo

Se formularon, de forma intuitiva, varias hipótesis sobre factores que podrían
mejorar el motor de asignación, y se validaron empíricamente sobre el conjunto
de 2000 escenarios comparando contra las dos líneas base.

Se **descartaron** la mayoría de las hipótesis iniciales. Solo tres parámetros
mostraron un efecto real y consistente:

1. **Selección crítica de la primera recogida** de cada voluntario. El punto de
   partida (su casa) es único y no se repite durante el resto del escenario; el
   primer viaje tiene un coste de oportunidad de ida que los siguientes no
   tienen. El motor prioriza las recogidas con **pocos voluntarios capaces de
   alcanzarlas** (exclusividad), con un peso `1/n_cap`.

2. **Ponderación positiva de las distancias muy lejanas** ("desierto"). Las
   recogidas lejanas a su centro son caras de rescatar y conviene no postergarlas
   indefinidamente. Bono suave a partir de un umbral de distancia.

3. **Ponderación negativa de las distancias muy cercanas** ("cercanía"). Las
   recogidas pegadas a su centro son viajes baratos que conviene despriorizar
   mientras quede tiempo. Es el espejo del caso anterior.

La fórmula de peso resultante (usada para puntuar cada viaje candidato antes del
emparejamiento) es:

```
peso = (comidas / duración)
       × (1 + BETA / n_cap)                       ← criticidad (exclusividad)
       × (1 + DESIERTO · m)                       ← bono de lejanía (m ∈ {1,2})
       × (1 − NEAR_K · (NEAR_KM − d)/NEAR_KM)     ← malus de cercanía
```

donde `n_cap` es el número de voluntarios capaces de rescatar esa recogida
(recalculado cada tick), y `m=2` cuando el voluntario sale de casa (primer viaje).

### 4.1 Ajuste fino de los parámetros

Se intentaron dos refinamientos, ambos **sin éxito**:

- **Modulación por escenario:** hacer depender los coeficientes (BETA, DESIERTO,
  NEAR_K) de los parámetros topológicos de cada escenario, para modular las
  reglas de forma específica. Resultado: **ninguna mejora** sobre los parámetros
  globales fijos. El óptimo de cada coeficiente resultó ser el mismo en los
  cuatro cuartiles de dificultad.

- **Ajuste fino del umbral exacto:** barrido masivo con incrementos pequeños de
  cada coeficiente. La variabilidad introduce ruido, pero las curvas son muy
  planas (meseta), así que se eligió un **punto medio** de la distribución con
  mayor % de recogida.

### 4.2 Valores finales de los parámetros

| Parámetro | Valor | Significado |
|---|---|---|
| `BETA` | **1.4** | Escala del bono de criticidad. Elegido como centro de la meseta 1.0–1.85 (validado por pares sobre semillas independientes: +0.22 pts significativos, sin degradar el peor caso). |
| `DESIERTO` | **0.2** | Bono por lejanía. Centro de la meseta 0.1–0.2. |
| `DESIERTO_KM` | **5.0** | Umbral de "desierto" (km). Centro de la meseta 4–6 km (robustez, no el pico). |
| `NEAR_K` | **0.5** | Malus por cercanía. Pico de la curva de campana. |
| `NEAR_KM` | **4.0** | Umbral de "cercanía" (km). |

### 4.3 Reserva de portador (explorada y refutada)

El diagnóstico de la sección 3.3 identificó un caso concreto donde el motor
pierde comida: un voluntario de capacidad 30 (el único con ventana larga) se
consume en recogidas pequeñas y luego no puede hacer las grandes que solo él
alcanza (en el escenario publicado, `v05` hace `r15/r27/r24` y pierde `r25`).
La hipótesis natural era una **reserva explícita de capacidad**: penalizar la
arista *(cap-30 → recogida pequeña)* mientras quede comida grande pendiente,
para "guardar" al portador escaso.

Se implementó como una **regla quirúrgica separada**, sin tocar el ratio
`comidas/duración` (que la sección 4 mostró esencial), y se validó a escala:

| Penalización (PENALTY) | Media (500 semillas OOS) | Δ vs motor | ↑/↓ |
|---|---|---|---|
| 0 (motor) | 56.19% | — | — |
| 0.3 | 56.00% | −0.19 | 95/104 |
| 0.5 | 55.77% | −0.43 | 102/140 |
| 0.7 | 55.58% | −0.62 | 99/162 |

**Resultado: la reserva resta, no suma.** La penalización degrada la media de
forma monótona y las regresiones superan a las mejoras. La causa: al quitarle al
cap-30 las recogidas pequeñas que *sí* puede hacer a tiempo, se deja escapar
comida sin garantía de que capture la grande. La señal de `sample_01` (un solo
escenario) **no generaliza** — es el mismo patrón que la modulación por
escenario (4.1): un hallazgo de un único caso no sobrevive a la validación en
muestra amplia.

Esto cierra la vía de la **reserva de capacidad local**: el coste de
oportunidad del portador no se captura con penalizaciones locales; exige ver el
futuro (lookahead global), que es exactamente lo que intenta el método de IA de
la sección 7.

### 4.4 Lookahead heurístico de 2–3 turnos sobre el motor (explorado y refutado)

La sección 4.3 dejó abierta una pregunta natural: si el matcher es miope
*entre* tics (cada tic re-resuelve sin memoria del acoplamiento secuencial),
¿por qué no darle una **mirada hacia delante**? La idea, en su formulación más
barata, no es enumerar matchings alternativos (prohibitivo), sino un **detector
de pérdida irremediable**: simular el dispatch del motor y los `K` tics
siguientes, detectar si alguna recogida que caduca dentro del horizonte queda
sin rescatar, y —si es así— **dar un peso extra** a esa recogida para que el
matching del tic actual la priorice (en lugar de quemar al voluntario que la
podía alcanzar).

Es la palanca que faltaba por probar en la familia "mirar el futuro", y la
última candidata a cerrar el gap secuencial sin IA.

**Diseño testeado** (`solver_lookahead.py`, en el repositorio principal):

1. `D = motor(estado)` — dispatch completo del tic (no arista a arista).
2. *Rollout determinista*: clon del simulador, aplicar `D`, avanzar `K` tics más
   con el propio motor como solver interno (cacheado por tic, determinista).
3. *Detección*: recogidas pendientes con `caduca_min ≤ t + (K+1)·5` que el
   rollout **no** rescató.
4. *Intervención (rama A)*: re-resolver el matching del tic con un factor
   multiplicativo `BOOST` sobre las aristas hacia esas recogidas en peligro.

Se barrió `K ∈ {1,2,3}` y `BOOST ∈ {1.5, 2.0, 3.0}` sobre **50 escenarios fuera
de muestra** (semillas 5001–5050).

**Resultado** (media de `porcentaje_salvado`; motor de referencia 55.76%):

| Configuración | Media | Δ vs motor | Gana |
|---|---|---|---|
| K=1 · BOOST 1.5/2.0/3.0 | 55.78% | +0.02 | 1/50 |
| K=2 · BOOST 1.5 | 55.80% | +0.03 | 2/50 |
| K=2 · BOOST 2.0 | 55.76% | −0.01 | 3/50 |
| K=2 · BOOST 3.0 | 55.72% | −0.05 | 3/50 |
| K=3 · BOOST 1.5 | 55.85% | +0.09 | 6/50 |
| K=3 · BOOST 2.0 | 55.65% | −0.11 | 7/50 |
| K=3 · BOOST 3.0 | 55.52% | −0.24 | 7/50 |

**Conclusión: refutado.** Todos los deltas están dentro del ruido (el mejor,
+0.09 en K=3/BOOST=1.5, es indistinguible de cero), y la dirección se vuelve
**negativa** conforme sube el `BOOST` (en `BOOST=3.0` empeora −0.05 y −0.24).
Es la misma firma que la reserva de portador (4.3): dar peso extra a ciegas
resta. El detector apenas dispara (el boost cambia el resultado en 1–7 de cada
50 escenarios), lo que confirma que la señal "esta recogida se pierde sin
remedio en 2 tics" no aparece con la frecuencia ni la fuerza que exigiría para
aportar.

**Lectura estructural.** Esto cierra la familia de heurísticas deterministas
"mirar hacia delante" —reserva de capacidad (4.3), rebalanceo de desierto y
cercanía (4.1), modulación por escenario (4.1) y ahora lookahead (4.4)— con el
mismo resultado: el coste de oportunidad secuencial **no se captura con pesos ni
heurísticas locales**. La única vía que sí lo hace es destilar la política del
óptimo global con el solucionador exacto, que es exactamente lo que persigue el
método de IA de la sección 7. Lejos de debilitarlo, el descarte del lookahead
refuerza la justificación de ese método: ninguna aproximación determinista al
futuro se le acerca.

---

## 5. Reproducibilidad

Todo el código está en el repositorio `crivote/food-rescue` (rama `main`). Los
escenarios se generan de forma determinista con el generador público
(`ai-for-good-72h-harness/comida/generar_escenario.py`), semilla explícita.

| Script | Qué hace |
|---|---|
| `firma_global.py` | Calcula los 10 parámetros topológicos de un escenario (sección 1.1). |
| `estratifica_cuartiles.py` | Particiona N escenarios en cuartiles de dificultad y mide greedy / matcher base / motor en cada uno (sección 2). |
| `bench_alcanzable.py` | Estimación simplificada (techo por ítem, sección 3.1). |
| `optimo_exacto.py` | Óptimo entero exacto de un escenario con CP-SAT (sección 3.3). |
| `solver_match_crit.py` | Motor final con los tres parámetros de mejora (sección 4). |
| `solver_match.py` | Matcher base (referencia culta). |
| `baseline_greedy.py` | Greedy del reto (referencia). |
| `valida_beta_14.py` | Validación por pares del parámetro BETA. |
| `ml/etiquetar_cpsat.py` | Genera el material de entrenamiento del scorer (sección 7). |
| `ml/scorer_features.py` | Fuente única de las features del scorer (locales + globales). |
| `ml/entrenar_variantes.py` | Entrena el scorer (LightGBM LambdaRank) y mide in-sample. |
| `ml/solver_scorer.py` | Motor online con el scorer aprendido en lugar del peso artesanal. |
| `ml/bench_estratificado.py` | Comparativa motor vs scorer fuera de muestra, por cuartiles. |

**Comandos de reproducción** (desde la raíz del repo, con `ortools` instalado):

```bash
# estratificación por cuartiles (n=2000, semillas 5001-7000)
BETA=1.4 python3 estratifica_cuartiles.py 2000 5001

# firma topológica de sample_01 frente a una muestra
python3 firma_global.py 2000 5001

# óptimo entero exacto del escenario publicado (semilla 1)
python3 optimo_exacto.py 1 60
```

---

## 6. Resumen de resultados

| Métrica | Valor |
|---|---|
| Greedy del reto (media) | 42–52% según cuartil |
| Matcher base (referencia culta) | 46–58% según cuartil |
| **Motor final** | **49.9–62.8% según cuartil** (media ~56%) |
| Mejora sobre el matcher base | +3.4 a +4.6 pts, estable en todos los cuartiles |
| Óptimo entero real (escenario publicado) | 61.8% (con cancelaciones) |
| Margen capturable restante | +6.4 pts en el escenario publicado |

El motor supera de forma consistente a ambas líneas base en los cuatro cuartiles
de dificultad, y el margen restante hasta el óptimo está **cuantificado** (~6.4
puntos en el caso publicado, una vez corregido el modelado del origen), lo que
permite decidir con datos si merece la pena seguir optimizando.

---

## 7. Método de IA: aprendizaje por imitación del óptimo (resultado medido)

> **Estado:** el scorer aprendido está **implementado y medido**, y la
> integración final es un **solucionador unificado** (`ml/solver_scorer.py`) que
> combina el scorer con un **guardrail cap-30** (salvaguarda de cola, sección
> 7.5): cuando el scorer comete un desperdicio de portador, se devuelve al motor
> determinista. Los resultados de las secciones 1–6 corresponden al motor
> determinista consolidado; el detalle técnico (features, modelo, entrenamiento)
> está en [`docs/AI_METHODS.md`](AI_METHODS.md).

### 7.1 Motivación: por qué los pesos locales tocan techo

La sección 4 mostró que el motor final (55.4%) mejora el matcher base pero no
llega al óptimo (61.8%). El diagnóstico (sección 3.3) dejó claro dónde está el
límite: el matcher es **local** — en cada tic optimiza el presente y no ve el
**coste de oportunidad futuro**. Dos ejemplos concretos en el escenario
publicado:

- **Reserva de capacidad.** Un voluntario de capacidad 30 (el único con ventana
  larga) se consume en recogidas pequeñas y luego no puede hacer las grandes que
  solo él alcanza. El matcher local no "reserva" al voluntario capaz.
- **Desperdicio de portador.** Un voluntario rápido y capaz se asigna a una
  recogida diminuta, sacrificando una grande que habría podido hacer.

Esto **no se arregla cambiando pesos** (sección 4.1: la modulación por escenario
no aportó nada). Es un defecto *secuencial*, no de calibración. Las dos vías
estudiadas para atacarlo fueron:

1. **Receding-horizon con CP-SAT online.** Resolver el subproblema restante a
   óptimo en cada tic. Funcionó (+4.3 pts en el caso publicado) pero se descartó
   por **no-reproducibilidad**: con `num_search_workers=8` CP-SAT devuelve una
   solución óptima distinta entre empates, y como compromete el primer movimiento
   de cada tic, eso produce trayectorias distintas para la misma entrada.
2. **Aprendizaje por imitación (behavioral cloning).** Aprender la *función de
   puntuación* del óptimo, destilando un modelo determinista. Es la vía elegida.

### 7.2 Arquitectura profesor–alumno

```
                    offline (una vez)                  online (runtime)
   escenarios ──► CP-SAT (optimo_exacto.py) ──► plan óptimo
                                                     │
                                                     ▼ etiquetado de aristas
                                              modelo de puntuación (scorer)
                                                     │ pesos fijos
                                                     ▼
                        decidir(estado) ──► scorer ──► min-cost flow ──► asignación
```

- **Profesor.** `optimo_exacto.py` resuelve cada escenario a óptimo entero con
  CP-SAT y produce el plan global correcto. Corre offline y es costoso (CPU,
  NP-difícil), pero solo se ejecuta una vez por escenario.
- **Alumno.** Un modelo de puntuación aprende a replicar la elección del
  profesor: dado un par `(voluntario, recogida)` con sus características, predice
  el peso que habría hecho que el profesor eligiera esa arista. Sustituye la
  **fórmula artesanal del peso** (sección 4), no la capa de emparejamiento.
- **Capa de emparejamiento intacta.** El `min-cost flow` (asignación bipartita)
  que ya existe en el motor sigue traduciendo los pesos a una asignación factible.
  Garantiza que toda salida sea válida (un voluntario un viaje, una recogida una
  vez) y que el resultado sea determinista.

**Por qué sí es determinista, a diferencia del receding-horizon.** El no-
determinismo del CP-SAT (múltiples óptimos empatados) solo afecta al *profesor*,
que corre offline y del que basta una solución óptima cualquiera. El *alumno*
tiene pesos fijos, así que la cadena online `scorer → min-cost flow` produce
siempre la misma salida para la misma entrada.

### 7.3 Material de entrenamiento generado

Para entrenar al alumno se generó un conjunto de escenarios resueltos a óptimo:

| Magnitud | Valor |
|---|---|
| Escenarios generados | 600 (semillas 20300–20899, nunca usadas en validación) |
| Resueltos a `OPTIMAL` | **572 (95.3%)** |
| `FEASIBLE` (subóptimo, se descarta al etiquetar) | 28 (4.7%) |
| Fallos / timeouts totales | 0 |
| Tiempo medio por escenario | ~22.8 s (mediana ~12 s), CPU |

Los planes se materializan con `etiquetar_cpsat.py` en `labels/planes.jsonl`
(cada línea: `{semilla, status, wall, pct, gap, plan[]}`). Solo se conservan las
semillas `OPTIMAL`; un plan subóptimo no debe enseñar al alumno.

### 7.4 Resultados medidos

Los pasos del plan (etiquetar aristas, entrenar el scorer, validar fuera de
muestra) se ejecutaron completos. El resumen, por configuración y conjunto de
medida:

| Conjunto | Motor | Scorer (locales) | Scorer (globales) |
|---|---|---|---|
| In-sample, 572 semillas | 55.97% | 58.04% (+2.07) | 58.17% (+2.20) |
| Fuera de muestra, 20 semillas | 55.88% | +1.22 | +1.49 |
| **Fuera de muestra, 1200 semillas** | **56.50%** | — | **57.24% (+0.74)** |

La comparativa definitiva es la de **1200 semillas fuera de muestra**,
estratificadas en los cuatro cuartiles de dificultad:

| Cuartil | n | Motor | Scorer | Δ |
|---|---|---|---|---|
| Q1 (fácil) | 300 | 62.69% | 63.30% | +0.61 |
| Q2 | 300 | 59.19% | 60.01% | +0.82 |
| Q3 | 300 | 54.74% | 55.46% | +0.72 |
| Q4 (difícil) | 300 | 49.38% | 50.20% | +0.82 |
| **Total** | **1200** | **56.50%** | **57.24%** | **+0.74** |

**Criterio de aceptación aplicado.** El scorer aprendido **sí** bate al motor
determinista de forma reproducible y fuera de muestra: gana en los **cuatro
cuartiles** (688/1200, 57.3%), sin degradar el peor caso. La mejora es modesta
pero **estable** (+0.61 a +0.82 pts), no un artefacto de muestra corta.

**Conclusión de la vía de IA.** El behavioral cloning es una mejora *real y
robusta* (+0.74 pts), pero **pequeña**: el margen in-sample (+2.2 pts) se reduce
fuera de muestra por overfitting parcial. Las variantes que intentaron ampliar
el objetivo no lo cerraron:

- **Features globales** (raciones pendientes, presión de capacidad, horizonte):
  aportan +0.13 pts in-sample, es decir, nada significativo. El +3.10 que
  sugería una submuestra de 100 era ruido.
- **Label ponderado por raciones**: sin efecto (hay un solo positivo por grupo,
  así que la magnitud no cambia el orden del ranking).
- **Más datos**: innecesario — con 572 semillas (240 k aristas) ya hay muestra
  suficiente; el límite es estructural, no de datos.

El límite de fondo se confirma: el profesor optimiza un plan **global**, y sus
etiquetas por tic solo codifican decisiones **locales**. El coste de oportunidad
de quemar un voluntario en una recogida pequeña no cabe en un ranking de aristas
individuales. Y tampoco lo captura una penalización local de reserva (sección
4.3): el margen restante (~6 pts) exige atacar la miopía secuencial con una
visión **global** del plan, no con pesos ni reservas locales.

### 7.5 Guardrail cap-30: salvaguarda de cola (paso final de integración)

Aunque el scorer gana en media, en **algunas semillas concretas** comete una
pifia que hunde ese escenario: desperdicia un voluntario de **capacidad 30** —el
único que puede rescatar las recogidas grandes— mandándolo a una recogida
pequeña. Como el evaluador final corre el solver sobre **unas pocas semillas
concretas**, una sola pifia puede costar caro. La salvaguarda no busca subir la
media (ya es modesta, +0.74 pts), sino **no cagarla** en un caso concreto.

**La regla** (determinista, por desacuerdo — no un segundo modelo):

> Si el scorer manda a un **cap-30** a una recogida **pequeña** (≤ 25 raciones)
> y el motor determinista lo mandaría a una **grande** (≥ 30 raciones), se
> entrega la decisión del motor para ese tic.

Dos detalles: (1) solo dispara en **desacuerdo** (si ambos coinciden, no se
toca nada — elimina los falsos positivos de la primera versión, que dañaba
−1.46 pts); (2) umbral 30, el más estricto del barrido (20→25→30), el único con
neto no negativo.

**Resultado (n=800, fuera de muestra, 5001–5800), medido sobre la cola** (la
métrica correcta para una salvaguarda):

- La pérdida media del **decil peor** cae de **−5.79 a −3.39 pts** (mitigación
  +2.40 pts), y el guardrail mitiga en **51 de 80** semillas del decil.
- En los **15 peores fallos** del scorer: mitiga 12, empata 3, **no empeora
  ninguno** (seed 5088: −11.1→−2.7; seed 5575: −10.6→−1.7).
- El nº de semillas perdiendo más de 5 pts frente al motor baja de 44 a 24.
- **Coste en media: nulo** (57.04%→57.17%, +0.13); **win/loss mejora** frente al
  motor (57.4%→60.8% victorias).

No es un trade-off: es una mejora "gratuita" de cola con coste nulo en media.
Implementado en `ml/solver_scorer.py` (`decidir(estado)` calcula scorer y motor
en paralelo y aplica la regla); configurable por `GUARDRAIL` / `GUARDRAIL_GRANDE`
/ `GUARDRAIL_PEQUENA`. Detalle completo en `AI_METHODS.md` §10.
