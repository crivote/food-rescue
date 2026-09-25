#!/usr/bin/env python3
# ── MATCHER BASE (REFERENCIA, no es la entrega) ────────────────────────
# Matching comidas/minuto sin heurísticas. Solo sirve de línea base (53.2%).
"""
Solver online v2 — matching óptimo por ronda (min-cost flow).

En cada tic, resuelve el emparejamiento bipartito (voluntarios libres × recogidas
pendientes) que maximiza las comidas asignadas, con aristas = viajes factibles.
Esto es el "emparejamiento global" real (no un greedy), y captura las dependencias
entre voluntarios (quién debe llevar qué para maximizar el total).

Peso de arista configurable:
  - "comidas"         : maximiza comidas totales de la ronda
  - "comidas/minuto"  : prioriza eficiencia (comidas por tiempo de voluntario)

Multi-viaje: tras entregar, el voluntario queda libre y reaparece en rondas
posteriores. El matching por ronda lo captura naturalmente.
"""
import math
from collections import deque

R = 6371.0
MODO = "comidas/minuto"  # "comidas" | "comidas/minuto"


def km(a, b):
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


class MCMF:
    def __init__(self, n):
        self.n = n
        self.g = [[] for _ in range(n)]

    def add(self, u, v, cap, cost):
        self.g[u].append([v, cap, cost, len(self.g[v])])
        self.g[v].append([u, 0, -cost, len(self.g[u]) - 1])

    def min_cost_flow(self, s, t, maxf=10 ** 9):
        flow, cost = 0, 0
        INF = float("inf")
        while flow < maxf:
            dist = [INF] * self.n
            dist[s] = 0
            inq = [False] * self.n
            prevv = [-1] * self.n
            preve = [-1] * self.n
            q = deque([s])
            inq[s] = True
            while q:
                u = q.popleft()
                inq[u] = False
                for i, e in enumerate(self.g[u]):
                    v, cap, c, _ = e
                    if cap > 0 and dist[v] > dist[u] + c:
                        dist[v] = dist[u] + c
                        prevv[v] = u
                        preve[v] = i
                        if not inq[v]:
                            q.append(v)
                            inq[v] = True
            if dist[t] == INF:
                break
            d = maxf - flow
            v = t
            while v != s:
                d = min(d, self.g[prevv[v]][preve[v]][1])
                v = prevv[v]
            flow += d
            cost += d * dist[t]
            v = t
            while v != s:
                e = self.g[prevv[v]][preve[v]]
                e[1] -= d
                self.g[v][e[3]][1] += d
                v = prevv[v]
        return flow, cost


def _mejor_centro(estado, recogida, voluntario, llega_recogida):
    mejor = None
    mejor_d = float("inf")
    for c in estado["centros"]:
        a_centro = km(recogida["pos"], c["pos"]) / voluntario["velocidad_kmh"] * 60
        llega_centro = llega_recogida + a_centro
        if llega_centro > c["cierra_min"]:
            continue
        if llega_centro > voluntario["hasta_min"]:
            continue
        d = km(recogida["pos"], c["pos"])
        if d < mejor_d:
            mejor_d = d
            mejor = c["id"]
    return mejor


def _pos_centro(estado, cid):
    for c in estado["centros"]:
        if c["id"] == cid:
            return c["pos"]
    return None


def _viaje(estado, v, r, minuto):
    """(centro_id, duracion_total) o None."""
    if not v["activo"] or v["libre_min"] > minuto or v["hasta_min"] <= minuto:
        return None
    if r["comidas"] > v["capacidad"]:
        return None
    salida = max(minuto, v["libre_min"])
    a_rec = km(v["pos"], r["pos"]) / v["velocidad_kmh"] * 60
    llega_rec = salida + a_rec
    if llega_rec > r["caduca_min"]:
        return None
    centro = _mejor_centro(estado, r, v, llega_rec)
    if centro is None:
        return None
    a_cen = km(r["pos"], _pos_centro(estado, centro)) / v["velocidad_kmh"] * 60
    duracion = (llega_rec - salida) + a_cen
    return centro, duracion


def decidir(estado):
    minuto = estado["minuto"]
    libres = [
        v for v in estado["voluntarios"]
        if v["activo"] and v["libre_min"] <= minuto and v["hasta_min"] > minuto
    ]
    pendientes = [r for r in estado["recogidas"] if not r["asignada"]]

    if not libres or not pendientes:
        return []

    # construir aristas factibles
    nv, nr = len(libres), len(pendientes)
    S = 0
    sink = 1 + nv + nr
    m = MCMF(sink + 1)
    for i, v in enumerate(libres):
        m.add(S, 1 + i, 1, 0)
        for j, r in enumerate(pendientes):
            viaje = _viaje(estado, v, r, minuto)
            if viaje is None:
                continue
            centro, duracion = viaje
            if MODO == "comidas/minuto":
                peso = r["comidas"] / duracion
            else:
                peso = r["comidas"]
            # maximizar peso = minimizar -peso (escalado para ints)
            m.add(1 + i, 1 + nv + j, 1, int(-peso * 1000))
    for j in range(nr):
        m.add(1 + nv + j, sink, 1, 0)

    m.min_cost_flow(S, sink)

    decisiones = []
    for i, v in enumerate(libres):
        # qué arista salió con flujo de v a alguna r
        for e in m.g[1 + i]:
            to, cap, cost, _ = e
            if cap == 0 and nv + 1 <= to <= nv + nr:  # flujo usado (cap original 1 -> 0)
                j = to - 1 - nv
                r = pendientes[j]
                viaje = _viaje(estado, v, r, minuto)
                decisiones.append({
                    "voluntario": v["id"], "recogida": r["id"],
                    "centro": viaje[0],
                })
                break
    return decisiones
