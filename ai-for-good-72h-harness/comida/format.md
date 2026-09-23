# Contrato · comida

## Lo que recibes

En cada tic (cada 5 minutos simulados), el estado completo:

```json
{
  "minuto": 1180,
  "recogidas":   [{"id": "r00", "pos": [40.47, -3.65], "comidas": 15,
                   "caduca_min": 1215, "asignada": false, "rescatada": false}],
  "voluntarios": [{"id": "v00", "pos": [40.41, -3.70], "libre_min": 1180,
                   "hasta_min": 1300, "velocidad_kmh": 11, "capacidad": 20,
                   "activo": true}],
  "centros":     [{"id": "c0", "pos": [40.38, -3.71], "cierra_min": 1260}]
}
```

Los minutos son desde medianoche: `1140` es las 19:00. Las posiciones son
`[lat, lon]` y las distancias, geodésicas.

## Lo que devuelves

Una lista de asignaciones. Puede ir vacía.

```json
[{"voluntario": "v03", "recogida": "r17", "centro": "c1"}]
```

## Cuándo se rechaza una asignación

- El voluntario ha cancelado, o la recogida ya está asignada.
- No le cabe: `comidas > capacidad`.
- Llega tarde a la recogida: ya ha caducado.
- Llega al centro después de que cierre.
- Se sale de su ventana de dos horas.

Rechazar no resta. El registro completo sale con `--registro`, con el motivo
de cada rechazo: úsalo para depurar.

## La métrica

```
puntuacion = porcentaje_salvado = 100 × comidas_rescatadas / comidas_totales
desempate  = comidas_por_hora   = comidas_rescatadas / horas_de_voluntario
```

**Manda el porcentaje salvado.** Se ordena por él, y las comidas por hora de
voluntario solo deciden entre dos asignadores que salvan lo mismo.
`simulate.py` los devuelve en ese orden y lo dice en `metrica_principal` y
`desempate`.

Las horas de voluntario son tiempo real de puerta a puerta: el viaje al
comercio más el viaje al centro. Mandar a alguien al otro lado de la ciudad a
por 6 comidas te cuesta el desempate aunque salves las 6.

Por qué no al revés: una división se gana por el denominador. Un asignador que
hace una sola recogida cercana y se para saca más comidas por hora que el
greedy dejando perderse más del 95 % de la comida.
