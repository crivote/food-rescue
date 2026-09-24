# Método de IA: aprendizaje por imitación del solucionador exacto

> Documento técnico. Describe el entrenamiento del modelo de puntuación
> (`scorer`) que sustituye a la fórmula artesanal del peso en el motor. Es el
> detalle de la sección 7 de `METODOLOGIA.md`. El motor determinista publicado
> sigue siendo la entrega principal; el scorer es una capa de IA **opcional** y
> medida, no un requisito.
>
> Los scripts de esta capa viven en la subcarpeta `ml/` (raíz del repo); los
> módulos del motor que reutilizan (`solver_match_crit`, `firma_global`,
> `optimo_exacto`) y el simulador del reto siguen en la raíz.

---

## 1. Qué se quiere aprender y por qué

El motor final (`solver_match_crit.py`) es un **matcher local**: en cada tic del
simulador resuelve un emparejamiento de coste mínimo (min-cost flow) usando una
fórmula de peso calibrada a mano:

```
peso = (comidas / duración)
       × (1 + BETA / n_cap)
       × (1 + DESIERTO · m)
       × (1 − NEAR_K · (NEAR_KM − d) / NEAR_KM)
```

Ese peso es **miope**: valora cada viaje candidato por su mérito inmediato y no
por su **coste de oportunidad futuro** (qué recogida sacrifica al consumir ahora
un voluntario capaz). El solucionador exacto (CP-SAT, `optimo_exacto.py`) sí ve
el plan completo y recupera **+6.4 pts** más que el motor en el escenario
publicado (55.4% → 61.8%).

La idea del *behavioral cloning*: en lugar de diseñar a mano una función de peso
que anticipe el futuro, **destilar la política del solucionador exacto a un
modelo de puntuación barato y determinista**.

---

## 2. Arquitectura profesor–alumno

```
        offline (una vez, CPU)                    online (runtime)
 escenarios ──► CP-SAT (optimo_exacto.py) ──► plan óptimo global
                                                 │
                                                 ▼ etiquetado de aristas
                                          modelo de puntuación (scorer)
                                                 │ pesos fijos
                                                 ▼
            decidir(estado) ──► scorer ──► min-cost flow ──► asignación
```

- **Profesor.** `optimo_exacto.py` resuelve cada escenario a óptimo entero. Es
  costoso (NP-difícil) y no-determinista (múltiples óptimos empatados), pero
  corre **offline** y basta una solución óptima cualquiera.
- **Alumno.** Un modelo de *ranking* aprende a puntuar cada arista
  `(voluntario, recogida)`. Sustituye la **fórmula del peso**, no la capa de
  emparejamiento: el `min-cost flow` sigue traduciendo los pesos a una
  asignación factible.
- **Determinismo por construcción.** El alumno tiene pesos fijos, así que la
  cadena online produce siempre la misma salida para la misma entrada. El
  "lottery" del profesor queda confinado al offline.

---

## 3. Material de entrenamiento

| Magnitud | Valor |
|---|---|
| Escenarios generados | 600 (semillas 20300–20899, nunca usadas en validación) |
| Resueltos a `OPTIMAL` | **572 (95.3%)** |
| `FEASIBLE` (subóptimo, descartado al etiquetar) | 28 (4.7%) |
| Timeouts | 0 |
| Tiempo por escenario | media ~22.8 s, mediana ~12 s (CPU, 16 hilos) |

Los planes se materializan con `ml/etiquetar_cpsat.py` en `labels/planes.jsonl`.
Solo las semillas `OPTIMAL` alimentan al alumno (un plan subóptimo enseñaría la
política equivocada).

---

## 4. Etiquetado estado → decisión

De cada plan óptimo se extrae, tic a tic, qué arista eligió el profesor entre
todas las **factibles**. El replays reproduce la factibilidad con el mismo
`_viaje` del motor, de modo que el conjunto de aristas candidatas es idéntico al
que el motor vería en runtime.

- **Positivo** (label `1`): la arista que el profesor asignó a ese voluntario
  en ese tic.
- **Negativo** (label `0`): las demás aristas factibles no elegidas.

Se obtienen **~240 000 aristas** etiquetadas, agrupadas en **~23 900 grupos**
(un grupo por cada `(voluntario, tic)`, con exactamente **un positivo** por
grupo). La magnitud del label no importa: al haber un solo positivo por grupo,
ponderar por raciones no cambia el orden (verificado: idéntico resultado).

---

## 5. Características (features)

Se usan **25 features** por arista, en dos bloques. La lista es la fuente única
de verdad compartida por etiquetado, entrenamiento y runtime
(`ml/scorer_features.py`).

### 5.1 Locales a la arista (18)

| Feature | Qué mide |
|---|---|
| `comidas`, `duracion`, `base` | Eficiencia inmediata del viaje (raciones, minutos, raciones/min). |
| `n_cap`, `exclusividad` | Cuántos voluntarios pueden rescatar esa recogida, y su inverso. |
| `d_v_r_km`, `d_r_centro_km` | Distancia voluntario→recogida y recogida→centro más cercano. |
| `en_partida` | Si el voluntario sale de casa o de un centro. |
| `desierto`, `cerca` | Indicadores de lejanía/cercanía (los umbrales del motor). |
| `slack_min` | Margen entre llegada y caducidad de la recogida. |
| `t_restante_v`, `capacidad_v`, `velocidad_v` | Estado del voluntario. |
| `grande` | Si la recogida excede 25 raciones (solo cap-30). |
| `n_libres`, `n_pend`, `caduca_en` | Presión del tic. |

### 5.2 Globales del tic (7)

Estas codifican el contexto que el profesor "ve" al optimizar globalmente:

| Feature | Qué mide |
|---|---|
| `raciones_pend` | Comida total aún sin asignar. |
| `n_grandes_pend`, `raciones_grandes_pend` | Cuántas recogidas grandes (>25) quedan, y cuánta comida representan. |
| `n_cap30_activos` | Cuántos voluntarios cap-30 quedan activos. |
| `horizonte_min` | Minutos hasta el cierre de los centros. |
| `presion_grande` | Comida grande pendiente ÷ capacidad grande disponible. |
| `racion_share` | Fracción de la comida pendiente que supone esta recogida. |

---

## 6. Modelo y entrenamiento

- **Algoritmo.** LightGBM con objetivo **LambdaRank** (`lambdarank`), métrica
  NDCG. Se eligió ranking (no clasificación binaria) porque el motor consume el
  score a través de un `min-cost flow` que **maximiza una suma de pesos**: lo
  que importa es el **orden** relativo de las aristas de cada grupo, no la
  probabilidad absoluta de ser elegida.
- **Agrupación.** Cada grupo de ranking es el conjunto de aristas factibles de
  un `(voluntario, tic)`, con un único positivo. LambdaRank optimiza
  directamente que el positivo quede por encima de los negativos del grupo.
- **Salida.** Un `Booster` de ~2.7 MB, con predicción de orden de microsegundos
  por arista. Se carga una vez y se guarda con `booster_.save_model()`.
- **Coste.** ~18–20 s de entrenamiento sobre las 572 semillas (240 k aristas).

---

## 7. Resultados medidos

### 7.1 In-sample (las 572 semillas de entrenamiento)

| Configuración | Motor | Scorer | Profesor | Δ vs motor |
|---|---|---|---|---|
| Solo features locales (18) | 55.97% | 58.04% | 63.93% | +2.07 |
| + features globales (25) | 55.97% | 58.17% | 63.93% | +2.20 |

Las features globales aportan solo **+0.13 pts** sobre las locales: el +3.10 que
se veía en una submuestra de 100 semillas era ruido de muestra corta.

### 7.2 Fuera de muestra

**Validación corta (20 semillas, selector fijo).** +1.49 pts con features
globales (12/20), +1.22 pts con solo locales (10/20). Muestra demasiado corta
para decidir: los deltas individuales oscilan entre −4.7 y +11.1 pts.

**Benchmark estratificado (1200 semillas, 5001–6200).** La comparativa
definitiva, por cuartiles de dificultad (misma estratificación estructural de
`METODOLOGIA.md`, independiente del solver):

| Cuartil | n | Motor | Scorer | Δ |
|---|---|---|---|---|
| Q1 (fácil) | 300 | 62.69% | 63.30% | +0.61 |
| Q2 | 300 | 59.19% | 60.01% | +0.82 |
| Q3 | 300 | 54.74% | 55.46% | +0.72 |
| Q4 (difícil) | 300 | 49.38% | 50.20% | +0.82 |
| **Total** | **1200** | **56.50%** | **57.24%** | **+0.74** |

El scorer **gana en los cuatro cuartiles** (688/1200, 57.3%), con un margen
estable de **+0.61 a +0.82 pts**.

---

## 8. Conclusión y lectura honesta

1. **El scorer es una mejora real y robusta.** Gana al motor determinista de
   forma consistente en los cuatro cuartiles de dificultad, fuera de muestra.
   No es ruido ni memorización (las 1200 semillas no se vieron en el
   entrenamiento).

2. **Pero es una mejora pequeña.** El +2.2 pts in-sample colapsa a **+0.74 pts**
   fuera de muestra: hay overfitting parcial, y el margen real es modesto.

3. **El behavioral cloning local toca techo estructural.** Ni más features
   (globales), ni labels ponderados, ni más datos cierran el gap de ~6 pts hasta
   el óptimo. La causa es de fondo: el profesor optimiza un plan **global**, y
   sus etiquetas por tic ("qué arista elegir") solo codifican decisiones
   **locales**. El coste de oportunidad de quemar un voluntario en una recogida
   pequeña no se puede expresar como un ranking de aristas individuales.

4. **Valor de diseño.** Como alternativa *barata* al solucionador pesado, el
   scorer cumple: predicción por arista en microsegundos, modelo de 2.7 MB, y
   una mejora neta de +0.74 pts sin ejecutar CP-SAT en runtime. Es una opción
   **incremental**, no el salto de la IA.

La vía que sí capturaría el margen restante (~6 pts) es atacar la **miopía
secuencial** directamente (lookahead determinista o reserva explícita de
capacidad), no mejorar el objetivo de un ranking local.
