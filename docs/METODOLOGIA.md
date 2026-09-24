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
**umbral superior**: cuánto se puede llegar a recuperar en cada escenario. No se
puede resolver el problema de forma óptima en todos los escenarios con los
medios disponibles (es NP-difícil), así que se usan **dos estimaciones** que
acotan el óptimo:

### 3.1 Estimación simplificada (techo por ítem)

Solo cuenta la comida que es **imposible** salvar por los requisitos de tiempo,
distancia y capacidad de cada voluntario, ignorando la contención (que un mismo
voluntario no puede hacer todos los viajes). Es un límite superior **holgado**:

- Media global: **~96%** (en el escenario publicado, solo 1 recogida de 43 es
  irrecuperable).

### 3.2 Estimación realista (grafo de itinerarios)

Construye un **grafo de itinerarios** por voluntario: secuencias
`casa → recogida → centro → recogida → centro → …`, con tiempos redondeados al
tick (5 min, redondeo **hacia arriba**, conservador) y respetando ventanas,
capacidad y la regla de que el primer viaje sale de casa y los siguientes de un
centro. Se resuelve como un problema de flujo/cubrimiento **relajando la
integralidad**: se permite que una recogida se "parta" entre dos viajes (algo
físicamente imposible), lo que **infla** el resultado.

Esta estimación es más apretada que la simplificada, pero **sigue estando por
encima del óptimo real**, porque permite partir recogidas. El óptimo real queda
**por debajo** de ella.

| Cuartil | Motor final | Estimación realista (LP) | Margen motor→est. |
|---|---|---|---|
| Q1 | 62.8% | 83.5% | +20.7 |
| Q2 | 58.9% | 79.7% | +20.8 |
| Q3 | 54.9% | 76.9% | +22.0 |
| Q4 | 49.9% | 68.8% | +18.9 |

### 3.3 El umbral real (integralidad)

La única relajación que queda en 3.2 es la **integralidad** (no partir
recogidas). Eliminarla convierte el problema en entero, que sí es NP-difícil,
pero **para un escenario concreto es resoluble** con un solucionador de
programación con restricciones (CP-SAT). Esto da el **óptimo real** de un
escenario.

> **Corrección de modelado (importante).** Una primera versión del solucionador
> exacto asumía que cada viaje "desde centro" salía del centro **más cercano a la
> siguiente recogida** (el voluntario podía "teletransportarse" entre centros
> entre dos viajes). El harness real, en cambio, fija al voluntario en el centro
> donde terminó el viaje anterior. Ese defecto **inflaba** el óptimo hasta 71.1%.
> Tras corregir el origen (cada viaje sale del centro donde terminó el anterior),
> el óptimo se validó **reproduciéndolo contra el harness real** (coincidencia
> exacta), obteniendo los valores de abajo.

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
mejora, pero es finito y medible — menor que lo que sugería la versión anterior
del análisis (que estaba inflada por el defecto de origen).

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
| `techo_realista.py` | Estimación realista por grafo de itinerarios con relajación LP (sección 3.2). |
| `optimo_exacto.py` | Óptimo entero exacto de un escenario con CP-SAT (sección 3.3). |
| `solver_match_crit.py` | Motor final con los tres parámetros de mejora (sección 4). |
| `solver_match.py` | Matcher base (referencia culta). |
| `baseline_greedy.py` | Greedy del reto (referencia). |
| `valida_beta_14.py` | Validación por pares del parámetro BETA. |
| `etiquetar_cpsat.py` | Genera el material de entrenamiento del scorer (sección 7). |

**Comandos de reproducción** (desde la raíz del repo, con `ortools` instalado):

```bash
# estratificación por cuartiles (n=2000, semillas 5001-7000)
BETA=1.4 python3 estratifica_cuartiles.py 2000 5001

# firma topológica de sample_01 frente a una muestra
python3 firma_global.py 2000 5001

# estimación realista (LP) sobre n escenarios
python3 techo_realista.py 600 5001

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

## 7. Plan de IA: aprendizaje por imitación del óptimo (en curso)

> **Estado:** experimental, **no integrado** en el motor publicado. Esta sección
> documenta el plan y el material ya generado; los resultados de las secciones
> 1–6 corresponden al motor determinista consolidado.

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

### 7.4 Pasos pendientes y criterio de aceptación

1. **Etiquetado de aristas.** De cada plan óptimo, derivar qué aristas
   `(voluntario, recogida)` eligió el profesor (positivo) y cuáles descartó
   (negativo), junto con las **características** de cada arista (comidas,
   duración, criticidad, tiempo restante del voluntario, cuántos otros pueden
   hacer esa recogida, etc.).
2. **Entrenar el scorer** sobre esas aristas etiquetadas.
3. **Validar fuera de muestra.** Medir el % de comida rescatada del motor con el
   scorer aprendido, en escenarios **no vistos** en el entrenamiento, contra el
   motor actual (55.4% publicado).

**Criterio de aceptación.** El scorer aprendido solo se integra si, de forma
**reproducible y fuera de muestra**, bate al motor determinista actual sin
degradar el peor caso. En caso contrario, se descarta y la entrega queda como
está (el motor local ya consolidado).
