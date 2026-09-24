#!/usr/bin/env python3
"""
Solver online con scorer aprendido (LightGBM) en lugar del peso artesanal.

Sustituye la fórmula peso = base × (1+bono) × ... por el score del modelo
entrenado. La capa de emparejamiento (min-cost flow) queda intacta, así que la
salida siempre es factible y determinista.

Las features se leen de scorer_features.py (fuente única), de modo que las
dimensiones coinciden exactamente con las del entrenamiento (entrenar_variantes.py).
Si cambias scorer_features.FEATURE_KEYS, reentrena el modelo para que el
predict no falle por desajuste de columnas.

El modelo se carga una vez (ruta en SCORER_MODEL o argumento). Si el modelo no
está disponible, devuelve [] (fallback: el orquestador usa el motor miope).

Uso (como módulo):
    from solver_scorer import decidir
"""
import os
import sys

# módulos del motor en la raíz del repo (padre de ml/)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from solver_match_crit import (MCMF, _viaje, _criticidad, _pos_centro,  # noqa: E402
                               _mejor_centro)
import scorer_features as sf  # noqa: E402

_modelo = None
_modelo_path = None


def cargar_modelo(ruta=None):
    global _modelo, _modelo_path
    if _modelo is not None and (ruta is None or ruta == _modelo_path):
        return _modelo
    # Prioridad de ruta: argumento explícito → variable de entorno → default.
    # El default apunta a un artefacto que NO se commitea (ver .gitignore):
    # regenerar con `bash ml/build_scorer.sh`. Si no existe, decidir() devuelve
    # [] (fallback silencioso al motor miope); el orquestador debe comprobar
    # la disponibilidad del modelo antes de invocar este solver.
    ruta = ruta or os.environ.get("SCORER_MODEL") or "labels/scorer_full.txt"
    import lightgbm as lgb
    _modelo = lgb.Booster(model_file=ruta)
    _modelo_path = ruta
    return _modelo


def decidir(estado):
    try:
        modelo = cargar_modelo()
    except Exception:
        return []  # fallback: sin modelo no se decide nada

    minuto = estado["minuto"]
    libres = [v for v in estado["voluntarios"]
              if v["activo"] and v["libre_min"] <= minuto and v["hasta_min"] > minuto]
    pendientes = [r for r in estado["recogidas"] if not r["asignada"]]
    if not libres or not pendientes:
        return []

    ncap = _criticidad(estado)
    n_libres = len(libres)
    n_pend = len(pendientes)
    activos = [v for v in estado["voluntarios"] if v["activo"]]
    ctx = sf.contexto_global(estado, minuto, pendientes, activos)

    nv, nr = len(libres), len(pendientes)
    S = 0
    sink = 1 + nv + nr
    m = MCMF(sink + 1)

    # precompute features -> score por arista
    for i, v in enumerate(libres):
        m.add(S, 1 + i, 1, 0)
        for j, r in enumerate(pendientes):
            feats = sf.features_arista(estado, v, r, minuto, ncap,
                                       n_libres, n_pend, ctx)
            if feats is None:
                continue
            score = float(modelo.predict([feats])[0])
            # coste = -score (el flow maximiza la suma de scores)
            m.add(1 + i, 1 + nv + j, 1, int(-score * 1000))
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
