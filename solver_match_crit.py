#!/usr/bin/env python3
# ── SOLVER DETERMINISTA (BACKUP del principal) ─────────────────────────
# Motor de reglas stdlib. NO es la entrega: actúa como base y salvaguarda
# del solucionador principal (ml/solver_scorer.py). Solo, da 55.4%.
"""
Solver online — matcher por ronda con prioridad de CRITICIDAD (exclusividad),
bono de DESIERTO (recogidas lejanas) y malus de CERCANÍA (recogidas pegadas
al centro).

Variante de solver_match.py. Añade al peso de cada arista TRES factores:

  (1) criticidad por exclusividad — bono que decae con n_cap = nº de
      voluntarios activos capaces de rescatar la recogida:
        peso = comidas/duracion * (1 + BETA * bono(n_cap))
      bono(n) configurable por CURVA:
        - power (default): BETA * n^-GAMMA   (GAMMA=1 -> 1/n, óptimo robusto)
        - step:            BETA si n==1, 0 si no
        - exp:             BETA * exp(-(n-1)/TAU)

  (2) desierto — bono para recogidas lejanas a su centro más cercano
      (> DESIERTO_KM), con el doble de fuerza si el voluntario está en su
      posición de partida (primer viaje = coste de oportunidad de ida):
        peso *= (1 + DESIERTO * (2 si en casa, 1 si re-despachado))

  (3) cercanía — malus para recogidas pegadas a su centro más cercano
      (< NEAR_KM): son viajes baratos que conviene despriorizar mientras quede
      tiempo. Es el espejo simétrico del desierto (misma lógica de gestionar el
      coste de viaje, vista por las dos caras):
        peso *= (1 - NEAR_K * (NEAR_KM - d_centro) / NEAR_KM)

La criticidad se recomputa cada tic (dinámica). Desierto y cercanía son
per-recogida y suaves: en un escenario sin recogidas lejanas/cercanas valen
exactamente 0 (no añaden ruido). Un factor modulado continuo bate a regímenes
binarios rígidos (verificado: selector binario +0.25 vs suave +0.58 fuera de
muestra).

Medido fuera de muestra (semillas 5001+, n=500):
  - criticidad 1/n: +2.2 ptos media vs matcher base
  - desierto 0.2:   +0.6 ptos media, +0.85 en decil peor
  - cercanía 0.5/4km: +0.78 ptos media (curva de campana, óptimo en 0.5)
Palancas descartadas con evidencia: CP-SAT lookahead, separación por tamaño
(lexicográfica), elección posicional de centro, reserva de portadores, selector
binario de desierto, término de margen/caducidad (urgencia), n_cap suave (slack),
acoplamiento criticidad↔desierto, dispatcher greedy secuencial.

Configurable por variables de entorno (BETA/CURVA/GAMMA/TAU/DESIERTO/DESIERTO_KM/
NEAR_K/NEAR_KM). Determinista, instantáneo, medible multi-semilla.
"""
import math
import os
from collections import deque

R = 6371.0
MODO = "comidas/minuto"

BETA = float(os.environ.get("BETA", "1.4"))    # escala del bono de criticidad
CURVA = os.environ.get("CURVA", "power")        # power | step | exp
GAMMA = float(os.environ.get("GAMMA", "1.0"))   # forma (solo CURVA=power)
TAU = float(os.environ.get("TAU", "1.0"))       # cte. de tiempo (solo CURVA=exp)
DESIERTO = float(os.environ.get("DESIERTO", "0.2"))   # escala del bono de desierto
DESIERTO_KM = float(os.environ.get("DESIERTO_KM", "5.0"))  # umbral de lejanía (km)
NEAR_K = float(os.environ.get("NEAR_K", "0.5"))       # escala del malus por cercanía
NEAR_KM = float(os.environ.get("NEAR_KM", "4.0"))     # umbral de cercanía (km)


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


def _puede_rescatar(estado, v, r):
    """¿Podría este voluntario rescatar r en algún momento (desde su posición
    actual), ignorando si ahora mismo está ocupado?"""
    if not v["activo"]:
        return False
    if r["comidas"] > v["capacidad"]:
        return False
    salida = v["libre_min"]
    a_rec = km(v["pos"], r["pos"]) / v["velocidad_kmh"] * 60
    llega_rec = salida + a_rec
    if llega_rec > r["caduca_min"]:
        return False
    # ¿algún centro abierto y dentro de ventana?
    for c in estado["centros"]:
        llega_cen = llega_rec + km(r["pos"], c["pos"]) / v["velocidad_kmh"] * 60
        if llega_cen <= c["cierra_min"] and llega_cen <= v["hasta_min"]:
            return True
    return False


def _criticidad(estado):
    """n_cap por recogida pendiente -> bono = 1/n_cap."""
    pendientes = [r for r in estado["recogidas"] if not r["asignada"]]
    activos = [v for v in estado["voluntarios"] if v["activo"]]
    ncap = {}
    for r in pendientes:
        n = sum(1 for v in activos if _puede_rescatar(estado, v, r))
        ncap[r["id"]] = n
    return ncap


def _bono(n):
    """Factor multiplicativo del peso según exclusividad n (nº de voluntarios capaces).
    Devuelve el multiplicador (>=1). CURVA controla la forma del decaimiento."""
    if n <= 0:
        n = 1
    if CURVA == "step":
        return BETA if n == 1 else 0.0
    if CURVA == "exp":
        return BETA * math.exp(-(n - 1) / TAU)
    return BETA * (n ** -GAMMA)  # power (default)


def _es_desierto(estado, r):
    """Recogida 'de desierto': lejana a su centro más cercano (> DESIERTO_KM)."""
    return min(km(r["pos"], c["pos"]) for c in estado["centros"]) > DESIERTO_KM


def _es_cerca(estado, r):
    """Recogida 'cercana': pegada a su centro más cercano (< NEAR_KM)."""
    return min(km(r["pos"], c["pos"]) for c in estado["centros"]) < NEAR_KM


def decidir(estado):
    minuto = estado["minuto"]
    libres = [
        v for v in estado["voluntarios"]
        if v["activo"] and v["libre_min"] <= minuto and v["hasta_min"] > minuto
    ]
    pendientes = [r for r in estado["recogidas"] if not r["asignada"]]

    if not libres or not pendientes:
        return []

    ncap = _criticidad(estado)
    # posiciones de los centros, para detectar si el voluntario está aún en casa
    centros_pos = {tuple(c["pos"]) for c in estado["centros"]}

    nv, nr = len(libres), len(pendientes)
    S = 0
    sink = 1 + nv + nr
    m = MCMF(sink + 1)
    for i, v in enumerate(libres):
        m.add(S, 1 + i, 1, 0)
        en_partida = tuple(v["pos"]) not in centros_pos
        for j, r in enumerate(pendientes):
            viaje = _viaje(estado, v, r, minuto)
            if viaje is None:
                continue
            centro, duracion = viaje
            base = r["comidas"] / duracion
            n = ncap.get(r["id"], 1)
            peso = base * (1.0 + _bono(n))
            # bono de desierto: doble si es primer viaje (oportunidad de ida)
            if _es_desierto(estado, r):
                mult = 2.0 if en_partida else 1.0
                peso *= (1.0 + DESIERTO * mult)
            # malus de cercanía: los viajes baratos al centro se despriorizan
            # (mientras quede tiempo); es el espejo simétrico del desierto.
            if _es_cerca(estado, r):
                d_centro = min(km(r["pos"], c["pos"]) for c in estado["centros"])
                peso *= (1.0 - NEAR_K * max(0.0, (NEAR_KM - d_centro) / NEAR_KM))
            m.add(1 + i, 1 + nv + j, 1, int(-peso * 1000))
    for j in range(nr):
        m.add(1 + nv + j, sink, 1, 0)

    m.min_cost_flow(S, sink)

    decisiones = []
    for i, v in enumerate(libres):
        for e in m.g[1 + i]:
            to, cap, cost, _ = e
            if cap == 0 and nv + 1 <= to <= nv + nr:
                j = to - 1 - nv
                r = pendientes[j]
                viaje = _viaje(estado, v, r, minuto)
                decisiones.append({
                    "voluntario": v["id"], "recogida": r["id"],
                    "centro": viaje[0],
                })
                break
    return decisiones
