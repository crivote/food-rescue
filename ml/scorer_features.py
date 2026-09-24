#!/usr/bin/env python3
"""
Features compartidas de arista (voluntario, recogida) para el scorer.

Fuente única de verdad para etiquetado, entrenamiento y runtime, de modo que
las features de entrenar y predecir no diverjan. Incluye:
  - features LOCALES de la arista (las 18 originales)
  - features GLOBALES del tick (contexto que el profesor "ve" al optimizar global)

FEATURE_KEYS es el orden exacto del vector numérico.
"""
import sys
import os

# los módulos del motor viven en la raíz del repo (padre de ml/)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from solver_match_crit import (km, _viaje, _criticidad,  # noqa: E402
                               _es_desierto, _es_cerca)

FEATURE_KEYS = [
    # locales a la arista
    "comidas", "duracion", "base", "n_cap", "exclusividad",
    "d_v_r_km", "d_r_centro_km", "en_partida", "desierto", "cerca",
    "slack_min", "t_restante_v", "capacidad_v", "velocidad_v", "grande",
    # contexto del tick
    "n_libres", "n_pend", "caduca_en",
    # contexto GLOBAL (nuevo)
    "raciones_pend", "n_grandes_pend", "raciones_grandes_pend",
    "n_cap30_activos", "horizonte_min", "presion_grande", "racion_share",
]


def contexto_global(estado, minuto, pendientes, activos):
    """Features globales del tick (comunes a todas las aristas del tick)."""
    raciones_pend = sum(r["comidas"] for r in pendientes)
    grandes = [r for r in pendientes if r["comidas"] > 25]
    n_grandes_pend = len(grandes)
    raciones_grandes_pend = sum(r["comidas"] for r in grandes)
    n_cap30 = sum(1 for v in activos if v["capacidad"] >= 30)
    # cierre global = max cierra_min (el simulador corre hasta cierre_min)
    cierre = max(c["cierra_min"] for c in estado["centros"])
    horizonte_min = cierre - minuto
    # presión de capacidad grande: comida grande pendiente / capacidad grande disponible
    presion = raciones_grandes_pend / max(1, n_cap30 * 30)
    return {
        "raciones_pend": raciones_pend,
        "n_grandes_pend": n_grandes_pend,
        "raciones_grandes_pend": raciones_grandes_pend,
        "n_cap30_activos": n_cap30,
        "horizonte_min": horizonte_min,
        "presion_grande": round(presion, 4),
    }


def features_arista(estado, v, r, minuto, ncap, n_libres, n_pend, ctx):
    """Vector de features de la arista (v, r). None si no factible."""
    viaje = _viaje(estado, v, r, minuto)
    if viaje is None:
        return None
    centro_id, duracion = viaje

    comidas = r["comidas"]
    base = comidas / duracion if duracion > 0 else 0.0
    n = ncap.get(r["id"], 1)

    d_v_r = km(v["pos"], r["pos"])
    a_rec = d_v_r / v["velocidad_kmh"] * 60
    salida = max(minuto, v["libre_min"])
    llega_rec = salida + a_rec

    d_r_centro = min(km(r["pos"], c["pos"]) for c in estado["centros"])
    centros_pos = {tuple(c["pos"]) for c in estado["centros"]}
    en_partida = tuple(v["pos"]) not in centros_pos

    es_desierto = _es_desierto(estado, r)
    es_cerca = _es_cerca(estado, r)

    slack = r["caduca_min"] - llega_rec
    t_restante = v["hasta_min"] - minuto
    grande = 1 if comidas > 25 else 0

    racion_share = comidas / max(1, ctx["raciones_pend"])

    return [
        comidas, round(duracion, 2), round(base, 4), n,
        round(1.0 / n, 4), round(d_v_r, 3), round(d_r_centro, 3),
        int(en_partida), int(es_desierto), int(es_cerca), round(slack, 1),
        t_restante, v["capacidad"], v["velocidad_kmh"], grande,
        n_libres, n_pend, r["caduca_min"] - minuto,
        ctx["raciones_pend"], ctx["n_grandes_pend"],
        ctx["raciones_grandes_pend"], ctx["n_cap30_activos"],
        ctx["horizonte_min"], ctx["presion_grande"],
        round(racion_share, 4),
    ]
