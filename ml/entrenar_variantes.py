#!/usr/bin/env python3
"""
Entrena y evalúa variantes del scorer con features AMPLIADAS (locales + globales)
y dos esquemas de label:
  - binario  : elegida=1, no=0 (el baseline actual)
  - raciones : elegida=comidas, no=0  (prioriza salvar más comida)

Para cada variante entrena LambdaRank y reporta un sanity in-sample rápido
(motor vs scorer vs profesor) sobre las semillas de entrenamiento, para ver si
las features globales / el label ponderado destilan MÁS del profesor que el
baseline (+2.07 pts).

Uso:
  python3 entrenar_variantes.py --planes labels/planes.jsonl \
      --max-seeds 100 --salida-dir /tmp/scorer_variantes
"""
import argparse
import copy
import json
import os
import sys

HARNESS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "ai-for-good-72h-harness", "comida")
sys.path.insert(0, HARNESS)
from generar_escenario import generar  # noqa: E402
from simulate import Simulador  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import solver_match_crit as smc  # noqa: E402
import scorer_features as sf  # noqa: E402

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402


def cargar_planes(ruta, max_seeds=None):
    planes = {}
    pcts = {}
    with open(ruta) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d["status"] != "OPTIMAL":
                continue
            planes[d["semilla"]] = d["plan"]
            pcts[d["semilla"]] = d["pct"]
            if max_seeds and len(planes) >= max_seeds:
                break
    return planes, pcts


def etiquetar_semilla(esc, plan, label_mode):
    sim = Simulador(esc)
    by_t = {}
    for (vid, t, rid, cid, com, origen) in plan:
        by_t.setdefault(t, []).append({"voluntario": vid, "recogida": rid, "centro": cid})

    X_rows, y_rows, group_rows = [], [], []

    for minuto in range(esc["apertura_min"], esc["cierre_min"] + 1, 5):
        for vid, cuando in sim.canceladas.items():
            if minuto >= cuando and sim.voluntarios[vid]["activo"]:
                sim.voluntarios[vid]["activo"] = False
        estado = sim.estado(minuto)
        decisiones = by_t.get(minuto, [])

        libres = [v for v in estado["voluntarios"]
                  if v["activo"] and v["libre_min"] <= minuto
                  and v["hasta_min"] > minuto]
        pendientes = [r for r in estado["recogidas"] if not r["asignada"]]
        if not libres or not pendientes:
            for d in decisiones:
                sim.aplicar(minuto, d)
            continue

        ncap = smc._criticidad(estado)
        decididos = {(d["voluntario"], d["recogida"]): None for d in decisiones}
        # valor en comidas de cada decisión
        val_dec = {(d["voluntario"], d["recogida"]):
                   next(r["comidas"] for r in estado["recogidas"]
                        if r["id"] == d["recogida"]) for d in decisiones}

        n_libres = len(libres)
        n_pend = len(pendientes)
        activos = [v for v in estado["voluntarios"] if v["activo"]]
        ctx = sf.contexto_global(estado, minuto, pendientes, activos)

        for v in libres:
            grupo = []
            for r in pendientes:
                feats = sf.features_arista(estado, v, r, minuto, ncap,
                                           n_libres, n_pend, ctx)
                if feats is None:
                    continue
                X_rows.append(feats)
                key = (v["id"], r["id"])
                if key in decididos:
                    y_rows.append(val_dec[key] if label_mode == "raciones" else 1.0)
                else:
                    y_rows.append(0.0)
                grupo.append(1)
            if grupo:
                group_rows.append(len(grupo))

        for d in decisiones:
            sim.aplicar(minuto, d)

    return X_rows, y_rows, group_rows


def entrenar(X, y, group):
    ranker = lgb.LGBMRanker(
        objective="lambdarank", n_estimators=400, learning_rate=0.05,
        num_leaves=63, min_child_samples=20, n_jobs=-1, random_state=42,
    )
    ranker.fit(X, y, group=group)
    return ranker


def correr_scorer(esc, booster):
    """Ejecuta el motor con el booster dado como scorer, retorna pct."""
    # solver_scorer carga por ruta; aquí inyectamos booster directamente
    from solver_scorer import MCMF, _viaje  # noqa: F401  (reusa)
    # reimplementamos decidir inline para usar booster sin fichero
    sim = Simulador(copy.deepcopy(esc))

    def decidir(estado):
        minuto = estado["minuto"]
        libres = [v for v in estado["voluntarios"]
                  if v["activo"] and v["libre_min"] <= minuto
                  and v["hasta_min"] > minuto]
        pendientes = [r for r in estado["recogidas"] if not r["asignada"]]
        if not libres or not pendientes:
            return []
        ncap = smc._criticidad(estado)
        n_libres = len(libres)
        n_pend = len(pendientes)
        activos = [v for v in estado["voluntarios"] if v["activo"]]
        ctx = sf.contexto_global(estado, minuto, pendientes, activos)
        nv, nr = len(libres), len(pendientes)
        S = 0
        sink = 1 + nv + nr
        m = MCMF(sink + 1)
        for i, v in enumerate(libres):
            m.add(S, 1 + i, 1, 0)
            for j, r in enumerate(pendientes):
                feats = sf.features_arista(estado, v, r, minuto, ncap,
                                           n_libres, n_pend, ctx)
                if feats is None:
                    continue
                score = float(booster.predict([feats])[0])
                m.add(1 + i, 1 + nv + j, 1, int(-score * 1000))
        for j in range(nr):
            m.add(1 + nv + j, sink, 1, 0)
        m.min_cost_flow(S, sink)
        out = []
        for i, v in enumerate(libres):
            for e in m.g[1 + i]:
                to, cap, cost, _ = e
                if cap == 0 and nv + 1 <= to <= nv + nr:
                    j = to - 1 - nv
                    r = pendientes[j]
                    viaje = _viaje(estado, v, r, minuto)
                    out.append({"voluntario": v["id"], "recogida": r["id"],
                                "centro": viaje[0]})
                    break
        return out

    res = sim.correr(decidir)
    return res["porcentaje_salvado"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--planes", default="labels/planes.jsonl")
    p.add_argument("--max-seeds", type=int, default=100)
    p.add_argument("--salida-dir", default="/tmp/scorer_variantes")
    a = p.parse_args()

    planes, pcts = cargar_planes(a.planes, a.max_seeds)
    semillas = sorted(planes.keys())
    os.makedirs(a.salida_dir, exist_ok=True)
    print(f"[variantes] {len(semillas)} semillas OPTIMAL", flush=True)

    resultados = {}
    for label_mode in ["binario", "raciones"]:
        print(f"\n=== label={label_mode} ===", flush=True)
        X_all, y_all, g_all = [], [], []
        for s in semillas:
            esc = generar(s)
            if s == semillas[0]:
                print(f"  [debug] s={s} type={type(s)} esc_keys={sorted(esc.keys())}", flush=True)
            X, y, g = etiquetar_semilla(esc, planes[s], label_mode)
            X_all.extend(X)
            y_all.extend(y)
            g_all.extend(g)

        X = np.array(X_all, dtype=float)
        y = np.array(y_all, dtype=float)
        group = np.array(g_all, dtype=int)
        print(f"  {X.shape[0]} aristas, {len(group)} grupos, "
              f"pos={int((y>0).sum())}", flush=True)

        booster = entrenar(X, y, group)

        # sanity in-sample: motor vs scorer vs profesor
        acc_motor = 0.0
        acc_scorer = 0.0
        acc_prof = 0.0
        n_bate = 0
        for s in semillas:
            esc = generar(s)
            r1 = Simulador(copy.deepcopy(esc)).correr(smc.decidir)
            sc = correr_scorer(esc, booster)
            m = r1["porcentaje_salvado"]
            prof = pcts[s]
            acc_motor += m
            acc_scorer += sc
            acc_prof += prof
            if sc > m:
                n_bate += 1

        n = len(semillas)
        delta = acc_scorer / n - acc_motor / n
        print(f"  [sanity in-sample n={n}] motor={acc_motor/n:.2f}% "
              f"scorer={acc_scorer/n:.2f}% prof={acc_prof/n:.2f}% "
              f"delta={delta:+.2f} | bate {n_bate}/{n}", flush=True)
        resultados[label_mode] = (acc_scorer / n, delta, n_bate)

        path = os.path.join(a.salida_dir, f"scorer_{label_mode}.txt")
        booster.booster_.save_model(path)

    print("\n=== RESUMEN VARIANTES ===")
    for k, (sc, delta, nb) in resultados.items():
        print(f"  {k}: scorer={sc:.2f}% delta={delta:+.2f} bate={nb}")


if __name__ == "__main__":
    main()
