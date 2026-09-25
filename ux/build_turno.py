#!/usr/bin/env python3
"""Regenera data/turno.json a partir de una corrida REAL del motor.

Corre el simulador del reto sobre el escenario y extrae el turno completo
del voluntario objetivo: sus misiones, raciones, horas de caducidad y los
kilometros/minutos de cada tramo (con la misma formula y la misma velocidad
que usa el simulador, para que las cifras coincidan con la traza).

Uso:  python3 build_turno.py [--voluntario v05] [--escenario sample_01]

Las rutas se resuelven de forma relativa a este fichero, para que el script
funcione en cualquier maquina que clone el repositorio.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
HARNESS = os.path.join(RAIZ, "ai-for-good-72h-harness", "comida")
SOLVER = os.path.join(RAIZ, "solver_match_crit.py")
SALIDA = os.path.join(AQUI, "data", "turno.json")

# El nombre que ve la voluntaria. Los datos son reales; el nombre, no.
ALIAS = "Juana España"


def km(a, b):
    """Distancia haversine en km, identica a la de simulate.py."""
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def correr_motor(escenario):
    """Corre el simulador y devuelve (registro, escenario, resultado)."""
    registro_path = tempfile.mktemp(suffix=".json")
    try:
        out = subprocess.run(
            [sys.executable, "simulate.py", "--scenario", escenario,
             "--solver", SOLVER, "--registro", registro_path],
            cwd=HARNESS, capture_output=True, text=True, check=True,
        )
        with open(registro_path, encoding="utf-8") as f:
            registro = json.load(f)
        with open(escenario, encoding="utf-8") as f:
            esc = json.load(f)
        return registro, esc, json.loads(out.stdout)
    finally:
        if os.path.exists(registro_path):
            os.unlink(registro_path)


def construir(registro, esc, voluntario):
    rec = {r["id"]: r for r in esc["recogidas"]}
    cen = {c["id"]: c for c in esc["centros"]}
    vol = {v["id"]: v for v in esc["voluntarios"]}[voluntario]

    misiones = [e for e in registro
                if e.get("ok") and e.get("voluntario") == voluntario]
    if not misiones:
        raise SystemExit(f"{voluntario} no tiene misiones en esta corrida.")

    vel = vol["velocidad_kmh"]
    pos = list(vol["pos"])
    tramos = []
    for i, m in enumerate(misiones, 1):
        rid, cid = m["recogida"], m["centro"]
        d_ida = km(pos, rec[rid]["pos"])
        d_vuelta = km(rec[rid]["pos"], cen[cid]["pos"])
        tramos.append({
            "orden": i,
            "t": m["min"],
            "recogida": rid,
            "centro": cid,
            "raciones": m["comidas"],
            "caduca_min": rec[rid]["caduca_min"],
            "km_ida": round(d_ida, 2),
            "min_ida": round(d_ida / vel * 60),
            "km_vuelta": round(d_vuelta, 2),
            "min_vuelta": round(d_vuelta / vel * 60),
        })
        # El voluntario deposita en el centro: la mision siguiente sale de ahi.
        pos = list(cen[cid]["pos"])

    return {
        "voluntario": {
            "alias": ALIAS,
            # La foto es PRESENTACION, no dato del motor: el alias y este
            # campo son lo unico de este bloque que no sale de la traza.
            "foto": "assets/juana-espana.webp",
            "capacidad": vol["capacidad"],
            "turno": [vol["desde_min"], vol["hasta_min"]],
        },
        "puntos_base": 260,
        "objetivo_turno": 50,
        "misiones": tramos,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--voluntario", default="v05")
    p.add_argument("--escenario", default="sample_01")
    a = p.parse_args()

    escenario = os.path.join(HARNESS, "scenarios", a.escenario + ".json")
    if not os.path.exists(escenario):
        raise SystemExit(f"No existe el escenario {escenario}")
    if not os.path.exists(SOLVER):
        raise SystemExit(f"No encuentro el asignador en {SOLVER}")

    registro, esc, res = correr_motor(escenario)
    turno = construir(registro, esc, a.voluntario)

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(turno, f, ensure_ascii=False, indent=2)

    total = sum(m["raciones"] for m in turno["misiones"])
    print(f"escenario      : {esc['nombre']} ({esc['ciudad']})")
    print(f"motor          : {res['porcentaje_salvado']}% "
          f"({res['comidas_rescatadas']}/{res['comidas_totales']})")
    print(f"voluntario     : {a.voluntario} -> {turno['voluntario']['alias']}")
    print(f"misiones       : {len(turno['misiones'])}")
    print(f"raciones       : {total}")
    print(f"km del turno   : {sum(m['km_ida'] + m['km_vuelta'] for m in turno['misiones']):.1f}")
    print(f"escrito        : {os.path.relpath(SALIDA, RAIZ)}")


if __name__ == "__main__":
    main()
