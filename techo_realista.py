#!/usr/bin/env python3
"""
ESTIMACIÓN REALISTA de la comida rescatable (LP time-indexed, origen EXACTO).

Relajación LP del problema real. El modelado de origen es EXACTO (sin teleport):
  - el primer viaje de cada voluntario sale de CASA (su posición inicial);
  - cada viaje posterior sale del CENTRO donde terminó el viaje anterior.

Eso se impone con un balance de flujo por centro (prefijo de salidas desde un
centro <= prefijo de llegadas a ese centro), idéntico al de optimo_exacto.py.

La ÚNICA relajación restante es la INTEGRALIDAD: una recogida puede "partirse"
entre varios viajes (físicamente imposible). Por eso esta estimación sigue
estando POR ENCIMA del óptimo entero real. El bracket es:

    motor  <=  óptimo entero real (optimo_exacto.py)  <=  esta estimación (LP)

Tiempos redondeados HACIA ARRIBA a múltiplo de 5 (conservador).

Uso: python3 techo_realista.py [n] [semilla_inicio]
"""
import math
import statistics
import sys

from ortools.linear_solver import pywraplp

HARNESS = "ai-for-good-72h-harness/comida"
sys.path.insert(0, HARNESS)
from generar_escenario import generar, km  # noqa: E402

import firma_global as fg  # noqa: E402

TICK = 5
CANCELA_MIN = 19 * 60 + 40  # 1180


def t_viaje(a, b, vel):
    """Tiempo de viaje (min) ceil a múltiplo de 5 (conservador)."""
    t = km(a, b) / vel * 60
    return int(math.ceil(t / 5.0) * 5)


def cota_escenario(esc):
    vols = {v["id"]: v for v in esc["voluntarios"]}
    recs = {r["id"]: r for r in esc["recogidas"]}
    cens = {c["id"]: c for c in esc["centros"]}
    centros_pos = {c["id"]: c["pos"] for c in cens.values()}
    cancelados = {c["voluntario"] for c in esc["cancelaciones"]}

    solver = pywraplp.Solver.CreateSolver("GLOP")
    if not solver:
        raise RuntimeError("GLOP no disponible")

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

            # viaje desde casa
            for rid in a_home:
                r = recs[rid]
                for c in cens.values():
                    a_cen = t_viaje(r["pos"], c["pos"], v["velocidad_kmh"])
                    llega_r = t + a_home[rid]
                    llega_c = llega_r + a_cen
                    if (llega_r <= r["caduca_min"] and llega_c <= c["cierra_min"]
                            and llega_c <= v["desde_min"] + 120):
                        var = solver.NumVar(
                            0.0, 1.0, f"H_{v['id']}_{t}_{rid}_{c['id']}")
                        viajes.append(dict(vid=v["id"], t=t, origen=None,
                                           rid=rid, cid=c["id"],
                                           dur=a_home[rid] + a_cen,
                                           llega=llega_c,
                                           comidas=r["comidas"], var=var))

            # viaje desde un centro concreto
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
                            var = solver.NumVar(
                                0.0, 1.0,
                                f"C_{v['id']}_{t}_{c_orig}_{r['id']}_{c['id']}")
                            viajes.append(dict(vid=v["id"], t=t, origen=c_orig,
                                               rid=r["id"], cid=c["id"],
                                               dur=a_orig + a_cen,
                                               llega=llega_c,
                                               comidas=r["comidas"], var=var))

    # (1) cada recogida a lo sumo una vez (relajado: <= 1, fraccionable)
    for rid in recs:
        ct = solver.Constraint(0.0, 1.0)
        for tr in viajes:
            if tr["rid"] == rid:
                ct.SetCoefficient(tr["var"], 1.0)

    # (2) no-solapamiento por voluntario (time-indexed)
    by_vid = {}
    for tr in viajes:
        by_vid.setdefault(tr["vid"], []).append(tr)
    for vid, trips in by_vid.items():
        for t_inst in ticks:
            ct = solver.Constraint(0.0, 1.0)
            for tr in trips:
                if tr["t"] <= t_inst < tr["t"] + tr["dur"]:
                    ct.SetCoefficient(tr["var"], 1.0)

    # (3) a lo sumo un viaje desde casa por voluntario
    for vid, trips in by_vid.items():
        ct = solver.Constraint(0.0, 1.0)
        for tr in trips:
            if tr["origen"] is None:
                ct.SetCoefficient(tr["var"], 1.0)

    # (4) balance de flujo por centro: Σ salidas <= Σ llegadas (prefijo).
    for vid, trips in by_vid.items():
        for cid in centros_pos:
            # acumulados por tick: dict tick -> lista de (var, coef)
            arr_by_tick = {}
            dep_by_tick = {}
            for tr in trips:
                if tr["cid"] == cid:
                    arr_by_tick.setdefault(tr["llega"], []).append(tr["var"])
                if tr["origen"] == cid:
                    dep_by_tick.setdefault(tr["t"], []).append(tr["var"])
            for t in ticks:
                # acumulado de llegadas - salidas debe ser >= 0 en todo tick:
                #  sum(arrivals hasta t) - sum(departures hasta t) >= 0
                ct = solver.Constraint(0.0, solver.infinity())
                for tt in arr_by_tick:
                    if tt <= t:
                        for var in arr_by_tick[tt]:
                            ct.SetCoefficient(var, 1.0)
                for tt in dep_by_tick:
                    if tt <= t:
                        for var in dep_by_tick[tt]:
                            ct.SetCoefficient(var, -1.0)

    # objetivo: maximizar comidas
    obj = solver.Objective()
    for tr in viajes:
        obj.SetCoefficient(tr["var"], float(tr["comidas"]))
    obj.SetMaximization()

    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL:
        return 0.0, sum(r["comidas"] for r in recs.values())

    total = sum(r["comidas"] for r in recs.values())
    return obj.Value(), total


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    ini = int(sys.argv[2]) if len(sys.argv) > 2 else 5001

    escs = [generar(s) for s in range(ini, ini + n)]
    firmas = [fg.firma(e) for e in escs]

    def z(vals):
        m = sum(vals) / len(vals)
        sd = (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5
        return [(x - m) / sd if sd else 0.0 for x in vals]

    z_alc = z([f["alcanzable_pct"] for f in firmas])
    z_cg = z([f["comida_grande_por_cap30"] for f in firmas])
    z_dr = z([f["d_rec_centro_media"] for f in firmas])
    dificultad = [-a + c + 0.5 * d for a, c, d in zip(z_alc, z_cg, z_dr)]
    idx = sorted(range(n), key=lambda i: dificultad[i])
    qs = [idx[i * n // 4:(i + 1) * n // 4] for i in range(4)]

    cotas = []
    for i, esc in enumerate(escs):
        r, tot = cota_escenario(esc)
        cotas.append(100.0 * r / tot)
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{n} ...", flush=True)

    print(f"\n=== ESTIMACIÓN REALISTA (ceil + origen EXACTO, LP) por cuartil ===")
    print(f"n={n} semillas ({ini}..{ini+n-1})")
    print(f"{'cuartil':8s} {'estim media':>12s} {'min':>6s} {'max':>6s} {'std':>6s}")
    for qi in range(4):
        vals = [cotas[i] for i in qs[qi]]
        print(f"Q{qi+1:7d} {statistics.mean(vals):11.1f}% "
              f"{min(vals):5.1f}% {max(vals):5.1f}% {statistics.pstdev(vals):5.1f}")

    print(f"\nestimación media global: {statistics.mean(cotas):.1f}%")


if __name__ == "__main__":
    main()
