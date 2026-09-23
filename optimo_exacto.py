#!/usr/bin/env python3
"""
ÓPTIMO ENTERO EXACTO del scheduling multi-viaje (CP-SAT, time-indexed binario).

Formulación CORREGIDA: modela el ORIGEN exacto de cada viaje. Cada voluntario
hace una secuencia de viajes (inicio -> recogida -> banco), donde:
  - el primer viaje sale de CASA (su posición inicial);
  - cada viaje posterior sale del CENTRO donde terminó el viaje anterior.

No hay "teleport" entre centros: para salir de un centro, hay que haber llegado
antes a ese centro. Se impone con una restricción de balance de flujo por
centro (D[v,c,t] <= A[v,c,t] para todo tick t): el prefijo de salidas desde un
centro nunca supera el prefijo de llegadas a ese centro.

Tiempos redondeados HACIA ARRIBA a múltiplos de 5 min (conservador), así que el
óptimo de este modelo es un LOWER BOUND del óptimo real del harness (nunca
sobre-estima por tiempos).

Uso: python3 optimo_exacto.py <semilla> [max_seconds] [--sin-cancelaciones]
"""
import argparse
import math
import sys

from ortools.sat.python import cp_model

HARNESS = "ai-for-good-72h-harness/comida"
sys.path.insert(0, HARNESS)
from generar_escenario import generar, km  # noqa: E402

TICK = 5
CANCELA_MIN = 19 * 60 + 40  # 1180


def t_viaje(a, b, vel):
    """Tiempo de viaje (min) ceil a múltiplo de 5 (conservador)."""
    t = km(a, b) / vel * 60
    return int(math.ceil(t / 5.0) * 5)


def resolver(esc, max_seconds=60.0, con_cancelaciones=True):
    vols = {v["id"]: v for v in esc["voluntarios"]}
    recs = {r["id"]: r for r in esc["recogidas"]}
    cens = {c["id"]: c for c in esc["centros"]}
    centros_pos = {c["id"]: c["pos"] for c in cens.values()}
    cancelados = (set() if not con_cancelaciones
                  else {c["voluntario"] for c in esc["cancelaciones"]})

    model = cp_model.CpModel()
    ticks = list(range(esc["apertura_min"], esc["cierre_min"] + 1, TICK))

    viajes = []  # dict(vid, t, origen, rid, cid, dur, llega, comidas, var)
    for v in vols.values():
        a_home = {}
        for r in recs.values():
            if r["comidas"] > v["capacidad"]:
                continue
            a_home[r["id"]] = t_viaje(v["pos"], r["pos"], v["velocidad_kmh"])

        for t in ticks:
            if t < v["desde_min"] or t >= v["desde_min"] + 120:
                continue
            if v["id"] in cancelados and t >= CANCELA_MIN:
                continue

            # viaje desde casa (origen = None)
            for rid in a_home:
                r = recs[rid]
                for c in cens.values():
                    a_cen = t_viaje(r["pos"], c["pos"], v["velocidad_kmh"])
                    llega_r = t + a_home[rid]
                    llega_c = llega_r + a_cen
                    if (llega_r <= r["caduca_min"] and llega_c <= c["cierra_min"]
                            and llega_c <= v["desde_min"] + 120):
                        var = model.NewBoolVar(f"H_{v['id']}_{t}_{rid}_{c['id']}")
                        viajes.append(dict(vid=v["id"], t=t, origen=None,
                                           rid=rid, cid=c["id"],
                                           dur=a_home[rid] + a_cen,
                                           llega=llega_c,
                                           comidas=r["comidas"], var=var))

            # viaje desde un centro concreto (origen = c_orig)
            for c_orig, c_orig_pos in centros_pos.items():
                for r in recs.values():
                    if r["comidas"] > v["capacidad"]:
                        continue
                    a_orig = t_viaje(c_orig_pos, r["pos"], v["velocidad_kmh"])
                    for c in cens.values():
                        a_cen = t_viaje(r["pos"], c["pos"], v["velocidad_kmh"])
                        llega_r = t + a_orig
                        llega_c = llega_r + a_cen
                        if (llega_r <= r["caduca_min"] and llega_c <= c["cierra_min"]
                                and llega_c <= v["desde_min"] + 120):
                            var = model.NewBoolVar(
                                f"C_{v['id']}_{t}_{c_orig}_{r['id']}_{c['id']}")
                            viajes.append(dict(vid=v["id"], t=t, origen=c_orig,
                                               rid=r["id"], cid=c["id"],
                                               dur=a_orig + a_cen,
                                               llega=llega_c,
                                               comidas=r["comidas"], var=var))

    # (1) cada recogida a lo sumo una vez
    for rid in recs:
        model.Add(sum(tr["var"] for tr in viajes if tr["rid"] == rid) <= 1)

    # (2) no-solapamiento por voluntario (time-indexed)
    by_vid = {}
    for tr in viajes:
        by_vid.setdefault(tr["vid"], []).append(tr)
    for vid, trips in by_vid.items():
        for t_inst in ticks:
            model.Add(sum(tr["var"] for tr in trips
                          if tr["t"] <= t_inst < tr["t"] + tr["dur"]) <= 1)

    # (3) a lo sumo un viaje desde casa por voluntario
    for vid, trips in by_vid.items():
        model.Add(sum(tr["var"] for tr in trips if tr["origen"] is None) <= 1)

    # (4) balance de flujo por centro: no salir de un centro sin haber llegado.
    #     Para cada (voluntario, centro, tick): Σ salidas <= Σ llegadas.
    for vid, trips in by_vid.items():
        for cid in centros_pos:
            arrivals = {}
            departures = {}
            for tr in trips:
                if tr["cid"] == cid:
                    arrivals.setdefault(tr["llega"], []).append(tr["var"])
                if tr["origen"] == cid:
                    departures.setdefault(tr["t"], []).append(tr["var"])
            cum_a = 0
            cum_d = 0
            for t in ticks:
                if t in arrivals:
                    cum_a = cum_a + sum(arrivals[t])
                if t in departures:
                    cum_d = cum_d + sum(departures[t])
                model.Add(cum_d <= cum_a)

    # objetivo: maximizar comidas
    model.Maximize(sum(tr["var"] * tr["comidas"] for tr in viajes))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    total = sum(r["comidas"] for r in recs.values())
    rescatable = int(round(solver.ObjectiveValue()))
    pct = 100.0 * rescatable / total

    plan = []
    for tr in viajes:
        if solver.Value(tr["var"]) > 0.5:
            plan.append((tr["vid"], tr["t"], tr["rid"], tr["cid"],
                         tr["comidas"], tr["origen"]))

    status_names = {cp_model.OPTIMAL: "OPTIMAL",
                    cp_model.FEASIBLE: "FEASIBLE",
                    cp_model.INFEASIBLE: "INFEASIBLE",
                    cp_model.UNKNOWN: "UNKNOWN"}
    gap = None
    if status == cp_model.OPTIMAL:
        gap = 0.0
    elif status == cp_model.FEASIBLE:
        gap = solver.BestObjectiveBound() - rescatable

    return (status_names.get(status, status), rescatable, total, pct,
            len(viajes), plan, solver.WallTime(), gap,
            solver.BestObjectiveBound())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("semilla", type=int, nargs="?", default=1)
    p.add_argument("max_seconds", type=float, nargs="?", default=60.0)
    p.add_argument("--sin-cancelaciones", action="store_true",
                   help="ignorar el calendario de cancelaciones")
    a = p.parse_args()
    esc = generar(a.semilla)

    modo = "SIN cancelaciones" if a.sin_cancelaciones else "CON cancelaciones"
    print(f"=== ÓPTIMO ENTERO EXACTO (CP-SAT, origen exacto) — {esc['nombre']} "
          f"(semilla {a.semilla}) [{modo}] ===\n")
    status, resc, total, pct, nvars, plan, wt, gap, bound = \
        resolver(esc, a.max_seconds, not a.sin_cancelaciones)

    print(f"estado solver : {status}")
    print(f"variables     : {nvars}")
    print(f"tiempo        : {wt:.1f}s")
    print(f"raciones      : {resc:.0f} / {total}")
    print(f"ÓPTIMO EXACTO : {pct:.1f}%")
    if gap is not None:
        print(f"gap           : {gap:.1f} raciones  (bound {bound:.0f})")

    if plan:
        print(f"\nplan ({len(plan)} viajes):")
        for (vid, t, rid, cid, com, origen) in sorted(plan,
                                                       key=lambda x: (x[0], x[1])):
            o = "casa" if origen is None else f"centro {origen}"
            print(f"  {vid}  t={t} ({o})  {rid} -> {cid}  {com} raciones")


if __name__ == "__main__":
    main()
