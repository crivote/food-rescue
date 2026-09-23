#!/usr/bin/env python3
"""
Firma global del escenario + localización de sample_01 en la distribución.

Objetivo: responder "¿mi 56% es representativo o favorable?" comparando la
topología GLOBAL de sample_01 contra la de N escenarios del mismo generador
(semillas 5001+, fuera de muestra).

Features globales (independientes del solver):
  G1  alcanzable_pct      : % de comida físicamente rescatable (techo por-ítem)
  G2  comida_grande       : % de comida en recogidas >25 (solo caben en cap-30)
  G3  comida_grande_por_cap30 : cuello de botella capacidad (ratio comida/cap30)
  G4  d_rec_centro_media  : distancia media recogida->centro más cercano
  G5  d_rec_centro_p90    : p90 de esa distancia (cola del desierto)
  G6  d_vol_rec_media     : distancia media voluntario->recogida más cercana
  G7  dispersion_rec      : nearest-neighbour medio entre recogidas (clustering)
  G8  dispersion_vol      : nearest-neighbour medio entre voluntarios
  G9  asimetria           : distancia centro-masa recogidas vs centro-masa centros
  G10 frac_caduca_temprano: % recogidas que caducan < 55 min

Para cada feature: media/min/max de la muestra, y el PERCENTIL donde cae
sample_01. Un percentil alto en G4/G5/G2 = sample_01 es "más difícil" que lo
típico -> mi 56% es conservador; percentil bajo = favorable.

También correlaciona cada feature global con el % salvado del motor actual.

Uso: python3 firma_global.py [n_semillas] [semilla_inicio]
"""
import importlib.util
import json
import math
import statistics
import sys

HARNESS = "ai-for-good-72h-harness/comida"
sys.path.insert(0, HARNESS)
from generar_escenario import generar  # noqa: E402
from simulate import Simulador, km   # noqa: E402


def _puede_desde_casa(v, r, centros):
    if r["comidas"] > v["capacidad"]:
        return False
    t = km(v["pos"], r["pos"]) / v["velocidad_kmh"] * 60
    llega_r = v["desde_min"] + t
    if llega_r > r["caduca_min"]:
        return False
    for c in centros:
        llega_c = llega_r + km(r["pos"], c["pos"]) / v["velocidad_kmh"] * 60
        if llega_c <= c["cierra_min"] and llega_c <= v["hasta_min"]:
            return True
    return False


def firma(esc):
    vols, recs, cens = esc["voluntarios"], esc["recogidas"], esc["centros"]
    total = sum(r["comidas"] for r in recs)
    ap = esc["apertura_min"]

    # G1 techo alcanzable
    rescatable = sum(r["comidas"] for r in recs
                     if any(_puede_desde_casa(v, r, cens) for v in vols))
    g1 = 100 * rescatable / total

    # G2 comida grande (>25, solo cap-30)
    g2 = 100 * sum(r["comidas"] for r in recs if r["comidas"] > 25) / total

    # G3 comida grande por cap30
    n_cap30 = sum(1 for v in vols if v["capacidad"] >= 30)
    comida_grande = sum(r["comidas"] for r in recs if r["comidas"] > 25)
    g3 = comida_grande / n_cap30 if n_cap30 else comida_grande

    # G4/G5 distancia recogida->centro
    d_rc = [min(km(r["pos"], c["pos"]) for c in cens) for r in recs]
    g4 = sum(d_rc) / len(d_rc)
    g5 = sorted(d_rc)[int(len(d_rc) * 0.9)]

    # G6 distancia voluntario->recogida más cercana
    d_vr = []
    for v in vols:
        d_vr.append(min(km(v["pos"], r["pos"]) for r in recs))
    g6 = sum(d_vr) / len(d_vr)

    # G7/G8 dispersión (nearest-neighbour medio)
    def nn(pts):
        if len(pts) < 2:
            return 0.0
        return sum(min(km(a, b) for j, b in enumerate(pts) if j != i)
                   for i, a in enumerate(pts)) / len(pts)
    g7 = nn([r["pos"] for r in recs])
    g8 = nn([v["pos"] for v in vols])

    # G9 asimetría: centro-masa recogidas vs centros
    def cm(pts):
        return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]
    cm_rec, cm_cen = cm([r["pos"] for r in recs]), cm([c["pos"] for c in cens])
    g9 = km(cm_rec, cm_cen)

    # G10 caducidad temprana
    g10 = 100 * sum(1 for r in recs if r["caduca_min"] - ap < 55) / len(recs)

    return {
        "alcanzable_pct": g1, "comida_grande": g2,
        "comida_grande_por_cap30": g3, "d_rec_centro_media": g4,
        "d_rec_centro_p90": g5, "d_vol_rec_media": g6,
        "dispersion_rec": g7, "dispersion_vol": g8,
        "asimetria": g9, "frac_caduca_temprano": g10,
    }


def cargar_ref():
    spec = importlib.util.spec_from_file_location("ref", "solver_match_crit.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.decidir


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    dy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    ini = int(sys.argv[2]) if len(sys.argv) > 2 else 5001

    # firma de sample_01
    esc01 = json.load(open(f"{HARNESS}/scenarios/sample_01.json"))
    f01 = firma(esc01)

    # firmas de la muestra + % salvado del motor
    ref = cargar_ref()
    firmas = []
    pcts = []
    keys = list(f01.keys())
    for s in range(ini, ini + n):
        esc = generar(s)
        f = firma(esc)
        firmas.append(f)
        pcts.append(Simulador(esc).correr(ref)["porcentaje_salvado"])

    print(f"muestra: {n} semillas ({ini}..{ini+n-1})\n")
    print(f"{'feature':26s} {'media':>7s} {'min':>7s} {'max':>7s} "
          f"{'sample01':>8s} {'percentil':>9s} {'pearson':>7s}")
    for k in keys:
        vals = [f[k] for f in firmas]
        media = sum(vals) / n
        vmin, vmax = min(vals), max(vals)
        v01 = f01[k]
        # percentil de sample_01 dentro de la muestra
        pctl = 100 * sum(1 for v in vals if v < v01) / n
        r = pearson(vals, pcts)
        print(f"{k:26s} {media:7.2f} {vmin:7.2f} {vmax:7.2f} "
              f"{v01:8.2f} {pctl:8.0f}% {r:+7.3f}")

    print(f"\n% salvado motor: media {sum(pcts)/n:.1f}  "
          f"min {min(pcts):.1f}  max {max(pcts):.1f}")
    print("percentil ~0 = sample_01 es el extremo 'fácil'; ~100 = extremo 'difícil'")
    print("pearson >0: la feature sube cuando el motor salva más; <0: lo dificulta")


if __name__ == "__main__":
    main()
