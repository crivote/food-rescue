#!/usr/bin/env python3
"""
Genera un escenario público reproducible.

La ciudad es sintética pero la geografía no: los puntos se siembran dentro
del recorte de Madrid que declara BBOX, con distancias en kilómetros reales
calculadas sobre la esfera. Eso importa porque el problema es de tiempos de
viaje, y un plano cartesiano en grados haría que moverse en longitud costara
menos que en latitud.

Determinista: misma semilla, mismo fichero. El escenario público se versiona
en scenarios/, así que cualquiera puede comprobar que no lo hemos tocado
después de publicar el número del baseline.
"""
import argparse
import json
import math
import random

# Madrid municipio, de Fuencarral a Villaverde. La primera versión usaba solo
# la almendra central y el greedy salvaba el 85 %: con todo a diez minutos, no
# hay problema que resolver. La ciudad real es esto, y a esta escala la
# distancia vuelve a costar.
BBOX = {"lat_min": 40.33, "lat_max": 40.51, "lon_min": -3.82, "lon_max": -3.58}

APERTURA_MIN = 19 * 60   # viernes 19:00
CIERRE_MIN = 22 * 60 + 30


def km(a, b):
    """Distancia en kilómetros entre dos (lat, lon)."""
    R = 6371.0
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def punto(rng):
    return [
        round(rng.uniform(BBOX["lat_min"], BBOX["lat_max"]), 5),
        round(rng.uniform(BBOX["lon_min"], BBOX["lon_max"]), 5),
    ]


def generar(semilla, n_recogidas=43, n_voluntarios=11, n_centros=6):
    rng = random.Random(semilla)

    recogidas = []
    for i in range(n_recogidas):
        # Las caducidades se reparten por toda la tarde. Una cola de cosas
        # que caducan muy pronto es lo que obliga a decidir qué se pierde.
        # Moda en 55 minutos: la mayoría de la comida aprieta pronto, que es
        # lo que obliga a elegir qué se pierde. Una distribución plana deja
        # tiempo para todo y el problema desaparece.
        caduca = APERTURA_MIN + int(rng.triangular(20, 180, 55))
        recogidas.append({
            "id": f"r{i:02d}",
            "pos": punto(rng),
            # Comidas, no kilos: la métrica se lee en personas alimentadas.
            "comidas": rng.choice([6, 8, 10, 12, 15, 18, 20, 25, 30]),
            "listo_min": APERTURA_MIN,
            "caduca_min": caduca,
        })

    voluntarios = []
    for i in range(n_voluntarios):
        inicio = APERTURA_MIN + rng.choice([0, 0, 15, 30])
        voluntarios.append({
            "id": f"v{i:02d}",
            "pos": punto(rng),
            "desde_min": inicio,
            # Dos horas es lo que da de sí un voluntario un viernes.
            "hasta_min": inicio + 120,
            # km/h puerta a puerta, ya descontando aparcar y subir.
            # Viernes a las siete en Madrid, puerta a puerta y contando
            # aparcar. Poner 18 km/h aquí sería regalar el problema.
            "velocidad_kmh": rng.choice([9, 11, 13, 15]),
            # Lo que carga de una vez.
            # Lo que carga uno de una vez. Que algunas recogidas grandes solo
            # le quepan a algunos es parte del problema de asignación.
            "capacidad": rng.choice([15, 20, 25, 30]),
        })

    centros = []
    for i in range(n_centros):
        centros.append({
            "id": f"c{i}",
            "pos": punto(rng),
            # La mitad cierran antes: son las ventanas que estrangulan.
            "cierra_min": 21 * 60 if i < 3 else 22 * 60,
            "capacidad": 200,
        })

    # Dos cancelaciones a las 19:40. No es un adorno: obliga a que el sistema
    # se replantee en caliente en vez de calcular un plan una sola vez.
    cancelaciones = [
        {"min": 19 * 60 + 40, "voluntario": voluntarios[2]["id"]},
        {"min": 19 * 60 + 40, "voluntario": voluntarios[7]["id"]},
    ]

    return {
        "nombre": f"sample_{semilla:02d}",
        "semilla": semilla,
        "ciudad": "Madrid (sintética sobre coordenadas reales)",
        "bbox": BBOX,
        "apertura_min": APERTURA_MIN,
        "cierre_min": CIERRE_MIN,
        "recogidas": recogidas,
        "voluntarios": voluntarios,
        "centros": centros,
        "cancelaciones": cancelaciones,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--semilla", type=int, default=1)
    p.add_argument("--salida", default="scenarios/sample_01.json")
    a = p.parse_args()
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(generar(a.semilla), f, ensure_ascii=False, indent=2)
    print(f"escrito {a.salida}")
