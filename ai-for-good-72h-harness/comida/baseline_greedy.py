#!/usr/bin/env python3
"""
Baseline · greedy por proximidad.

Lo que haría cualquiera sin pensarlo mucho: en cuanto un voluntario está
libre, mándalo a lo más cercano que caduque pronto. Sin mirar más allá del
siguiente viaje, sin agrupar, sin reservar a nadie para lo que viene.

Es un baseline honesto, no un hombre de paja: prioriza por urgencia, no coge
lo que no le da tiempo a alcanzar y elige el centro más cercano que siga
abierto. Perder contra esto significa que tu sistema es peor que el sentido
común, y batirlo por poco significa que aún hay sitio.

Lo que deja sobre la mesa, y donde está el reto:
  · nunca agrupa dos recogidas cercanas en un viaje
  · no reserva al voluntario rápido para la recogida lejana que caduca tarde
  · no sacrifica una recogida pequeña para salvar dos grandes
  · reacciona a las cancelaciones sin replantear lo ya decidido
"""
import math

VENTANA_URGENCIA = 45  # minutos: por debajo de esto, manda la urgencia


def km(a, b):
    R = 6371.0
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def decidir(estado):
    minuto = estado["minuto"]
    decisiones = []

    pendientes = [r for r in estado["recogidas"] if not r["asignada"]]
    libres = [
        v for v in estado["voluntarios"]
        if v["activo"] and v["libre_min"] <= minuto and v["hasta_min"] > minuto
    ]

    # Los que se van antes, primero: si no los usas ahora, los pierdes.
    libres.sort(key=lambda v: v["hasta_min"])
    tomadas = set()

    for v in libres:
        candidatos = []
        for r in pendientes:
            if r["id"] in tomadas or r["comidas"] > v["capacidad"]:
                continue

            viaje = km(v["pos"], r["pos"]) / v["velocidad_kmh"] * 60
            if minuto + viaje > r["caduca_min"]:
                continue  # no llega

            centro = _centro_mas_cercano(estado, r, v, minuto + viaje)
            if centro is None:
                continue

            candidatos.append((r, viaje, centro))

        if not candidatos:
            continue

        # "Lo más cercano que caduque antes": la urgencia manda, pero solo
        # cuando de verdad aprieta; si todo caduca tarde, decide la distancia.
        margen_min = min(c[0]["caduca_min"] for c in candidatos) - minuto

        if margen_min < VENTANA_URGENCIA:
            candidatos.sort(key=lambda c: (c[0]["caduca_min"], c[1]))
        else:
            candidatos.sort(key=lambda c: (c[1], c[0]["caduca_min"]))

        recogida, _, centro = candidatos[0]
        tomadas.add(recogida["id"])
        decisiones.append({
            "voluntario": v["id"], "recogida": recogida["id"], "centro": centro,
        })

    return decisiones


def _centro_mas_cercano(estado, recogida, voluntario, llegada_min):
    """El más cercano a la recogida que siga abierto cuando llegue."""
    mejor, mejor_dist = None, float("inf")
    for c in estado["centros"]:
        viaje = km(recogida["pos"], c["pos"]) / voluntario["velocidad_kmh"] * 60
        if llegada_min + viaje > c["cierra_min"]:
            continue
        if llegada_min + viaje > voluntario["hasta_min"]:
            continue
        d = km(recogida["pos"], c["pos"])
        if d < mejor_dist:
            mejor, mejor_dist = c["id"], d
    return mejor
