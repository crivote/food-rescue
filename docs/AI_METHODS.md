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

> **Nota sobre las dos validaciones fuera de muestra del repo.** El motor
> determinista está medido sobre **2000 escenarios** (semillas 5001–7000, ver
> `METODOLOGIA.md` §2) y arroja, en Q1, **62.8%**. El scorer se mide sobre una
> submuestra de **1200 escenarios** (semillas 5001–6200, las primeras 300 de
> cada cuartil) y arroja **62.69%** para el motor y **63.30%** para el scorer
> en Q1. Son benchmarks distintos con semillas y tamaños distintos: la
> diferencia de 0.11 pts en Q1 entre el 62.8% del README y el 62.69% de esta
> tabla refleja eso, no una inconsistencia. El tamaño importa: el +0.74 pts
> del scorer es estable en los **cuatro cuartiles** dentro de la misma
> muestra de 1200.

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
secuencial** directamente con una visión global del plan. Se verificó que la
reserva explícita de capacidad (penalizar al portador cap-30 en recogidas
pequeñas) **no** funciona a escala — resta, no suma (ver `METODOLOGIA.md`,
sección 4.3) — así que el límite no es de pesos ni de reservas locales, sino
estructural.

---

## 9. Transparencia (XAI) — decisión de diseño

Evaluamos la propuesta de usar **SHAP** (valores de Shapley) para explicar las
decisiones y cerrar el bloque de "IA responsable" del reto. **Conclusión: no se
aplica al motor, y en el scorer aporta poco más que la explicación analítica
que ya tenemos.**

- **El motor determinista no es un modelo que SHAP pueda explicar.** La función
  de peso es una fórmula aritmética de 4 factores, transparente por
  construcción: `peso = (raciones/min) × escasez × desierto × cercanía`. SHAP
  descompone la salida de un *modelo* en contribuciones de *features*; no hay
  features aprendidas en el motor, así que su explicación natural es la propia
  fórmula, no una descomposición de Shapley forzada.
- **En el scorer sí tendría sentido técnico** (`TreeExplainer` sobre el Booster
  LightGBM), pero el coste supera el valor: lo que importa en runtime es que el
  min-cost flow maximice la suma de scores, y el *porqué* de cada score ya se
  lee en la lista de 25 features. SHAP sería una visualización *post-hoc* — no
  participa en la decisión, así que no suma al criterio de "IA fundamental".
- **La transparencia que sí aporta valor es traducir la decisión a lenguaje
  natural.** En el prototipo de UX (`ux/`), la tarjeta de misión explica *por
  qué* se asignó esa recogida a ese voluntario. Esa frase no es un texto
  hardcodeado: la genera un **mecanismo** reproducible (`explicar_decision.py`),
  descrito a continuación.

### 9.1 Mecanismo de conversión a lenguaje natural

El motor ya computa, al decidir, los campos que *justifican* la asignación
(raciones, capacidad del voluntario, cuántos voluntarios podían llevar esa
recogida —el `n_cap` de la criticidad— y cuánto falta para que caduque). Esos
campos forman un **contexto de decisión estructurado**. La conversión a frase
natural es un pipeline de tres pasos, donde el LLM solo *traduce*, sin intervenir
en la decisión:

```
contexto JSON ──► prompt few-shot ──► LLM barato ──► frase natural
 (del motor)       (2 ejemplos)       (LLM barato)
                                         │ fallo de red/clave
                                         ▼
                                  plantilla determinista
```

- **Contexto.** `solver_match_crit.py` expone, para cada asignación, un JSON con
  `{raciones, capacidad_voluntario, voluntarios_capaces, min_para_caducar}` — los
  mismos valores que entran en la fórmula del peso, sin jerga.
- **Prompt few-shot.** `explicar_decision.py` mete ese JSON en un prompt con dos
  ejemplos `contexto → frase`, instruyendo a no usar términos técnicos y a no
  inventar datos. Los ejemplos enseñan a distinguir *escasez* ("eres el único")
  de *urgencia* ("caduca en 20 min").
- **Modelo.** Un LLM ligero a través de un endpoint OpenAI-compatible
  (configurado por variables de entorno `LLM_ENDPOINT` / `LLM_MODEL` /
  `LLM_API_KEY`; ninguna credencial ni nombre de proveedor va en el código). Una
  llamada de ~1 s y ~120 tokens por explicación.
- **Fallback determinista.** Si no hay red o clave, devuelve una plantilla
  equivalente (nunca deja de responder), marcando el aviso en `stderr`.

**Salida real verificada** (dos casos, LLM ligero OpenAI-compatible):

| Contexto | Frase generada |
|---|---|
| 30 raciones · cap 30 · 1 capaz · 45 min | «Eres la única persona capaz de recoger estas 30 raciones antes de que caduquen, ¡gracias por ayudarnos!» |
| 18 raciones · cap 25 · 3 capaces · 20 min | «Te hemos asignado estas 18 raciones porque tienes capacidad para llevarlas y quedan solo 20 minutos para que caduquen.» |

El segundo caso demuestra generalización (no repetición del ejemplo): ante tres
voluntarios capaces el modelo explica por *urgencia* en lugar de por *escasez*.

Se descarta SHAP como núcleo de la propuesta; queda registrada como opción
explorada, con la razón de su descarte. La explicabilidad real de cara al
usuario es este pipeline de traducción, que es transparente por construcción y
no participa en la decisión.
