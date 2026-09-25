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

El modelo se carga una vez (ruta resuelta respecto a la raíz del repo, o vía
SCORER_MODEL / argumento). Si el modelo no está disponible, se AVISA por stderr
y decidir() devuelve [] (el orquestador usa entonces el motor determinista): sin
ese aviso, quien mide creería estar obteniendo las cifras del integrado cuando en
realidad son las del motor determinista.

Uso (como módulo):
    from solver_scorer import decidir
"""
import os
import sys

# módulos del motor en la raíz del repo (padre de ml/)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
# scorer_features vive junto a este módulo (ml/); añadirlo para que el import
# funcione también al cargar el solver directamente vía `simulate.py --solver`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solver_match_crit import (MCMF, _viaje, _criticidad, _pos_centro,  # noqa: E402
                               _mejor_centro, decidir as decidir_motor)
import scorer_features as sf  # noqa: E402

_modelo = None
_modelo_path = None

# ── Guardrail cap-30 ───────────────────────────────────────────────────────
# Regla de salvaguarda (tail-risk), no de mejora de media: cuando el scorer y
# el motor determinista DISCREPAN sobre a qué recogida mandar a un voluntario
# de capacidad 30 — concretamente, el scorer lo manda a una recogida pequeña
# (≤ GUARDRAIL_PEQUEÑA raciones) y el motor lo mandaría a una grande
# (≥ GUARDRAIL_GRANDE raciones, que solo un cap-30 puede llevar) — se descarta
# la asignación del scorer para ese tic y se entrega la del motor. Evita el
# "desperdicio de portador" (quemar al único voluntario capaz en una recogida
# diminuta sacrificando una grande que nadie más puede rescatar).
#
# Medido fuera de muestra (n=800, semillas 5001..5800) sobre la métrica que
# importa — el PEOR CASO, no la media — el guardrail recorta los fallos gordos:
# la pérdida media del decil peor pasa de −5.79 a −3.39 pts, y en los 15 peores
# fallos del scorer mitiga 12 sin empeorar ninguno. En media y en win/loss no
# daña (ver docs/AI_METHODS.md §10).
GUARDRAIL_HABILITADO = os.environ.get("GUARDRAIL", "1") != "0"
GUARDRAIL_GRANDE = int(os.environ.get("GUARDRAIL_GRANDE", "30"))   # recogida grande
GUARDRAIL_PEQUENA = int(os.environ.get("GUARDRAIL_PEQUENA", "25"))  # recogida pequeña


def _scorer_quema_cap30(estado, decisiones_scorer):
    """Condición necesaria (barata) para que el guardrail pueda disparar:
    (a) el scorer ha mandado a algún voluntario cap-30 a una recogida pequeña
    (≤ GUARDRAIL_PEQUENA), y (b) existe al menos una recogida grande
    (≥ GUARDRAIL_GRANDE) pendiente. Si falta cualquiera de las dos, el motor no
    podría mandar al cap-30 a una grande y el guardrail jamás dispararía, así
    que no hace falta calcularlo."""
    cap = {v["id"]: v["capacidad"] for v in estado["voluntarios"]}
    comidas = {r["id"]: r["comidas"] for r in estado["recogidas"] if not r["asignada"]}
    quema = any(cap.get(d["voluntario"], 0) >= 30
                and comidas.get(d["recogida"], 0) is not None
                and comidas[d["recogida"]] <= GUARDRAIL_PEQUENA
                for d in decisiones_scorer)
    if not quema:
        return False
    hay_grande_pendiente = any(c >= GUARDRAIL_GRANDE for c in comidas.values())
    return hay_grande_pendiente


def _desacuerdo_cap30(estado, decisiones_scorer, decisiones_motor):
    """True si el scorer desperdicia un cap-30 en una recogida pequeña y el motor
    lo mandaría a una grande. Solo se dispara en DESACUERDO: si ambos coinciden
    en mandar al cap-30 a la pequeña, no se toca nada (evita falsos positivos).
    Requiere que ya se haya comprobado _scorer_quema_cap30."""
    comidas = {r["id"]: r["comidas"] for r in estado["recogidas"]}
    motor_por_vol = {d["voluntario"]: d["recogida"] for d in decisiones_motor}
    for d in decisiones_scorer:
        if comidas.get(d["recogida"], 0) > GUARDRAIL_PEQUENA:  # scorer no lo quema
            continue
        r_motor = motor_por_vol.get(d["voluntario"])
        if r_motor is not None and comidas.get(r_motor, 0) >= GUARDRAIL_GRANDE:
            return True
    return False


def cargar_modelo(ruta=None):
    global _modelo, _modelo_path
    if _modelo is not None and (ruta is None or ruta == _modelo_path):
        return _modelo
    # Prioridad de ruta: argumento explícito → variable de entorno → default.
    # El default apunta al modelo VERSIONADO en el repo (models/scorer_full.txt,
    # 2.7 MB, ~4h de regenerar), resuelto de forma ABSOLUTA respecto a la raíz
    # del repo (RAIZ), nunca respecto al cwd: si no, ejecutar el solver desde
    # otro directorio no encuentra el modelo y cae al motor sin avisar.
    if ruta:
        ruta = os.path.abspath(ruta)
    elif os.environ.get("SCORER_MODEL"):
        ruta = os.path.abspath(os.environ["SCORER_MODEL"])
    else:
        ruta = os.path.join(RAIZ, "models", "scorer_full.txt")
    import lightgbm as lgb
    try:
        _modelo = lgb.Booster(model_file=ruta)
    except Exception as exc:
        # NO tragarse el error: sin modelo, decidir() devolvería el motor
        # determinista y el evaluador creería estar midiendo el integrado.
        print("[solver_scorer] AVISO: no se pudo cargar el modelo en %r (%s). "
              "El scorer cae al motor determinista, asi que las cifras seran "
              "las del motor, NO las del solucionador integrado." % (ruta, exc),
              file=sys.stderr)
        raise
    _modelo_path = ruta
    return _modelo


def _decidir_scorer(estado):
    """Decisión del scorer puro (sin guardrail): scorer → min-cost flow."""
    try:
        modelo = cargar_modelo()
    except Exception:
        # cargar_modelo ya ha avisado por stderr y ha re-lanzado; aqui se
        # degrada al motor determinista de forma EXPLICITA y ruidosa (nunca
        # silenciosa: un fallback mudo falsearia la comparacion con el motor).
        print("[solver_scorer] AVISO: sin modelo, este tic lo decide el motor "
              "determinista (las cifras NO seran las del integrado).",
              file=sys.stderr)
        return []

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


def decidir(estado):
    """Solver unificado: scorer + guardrail cap-30.

    Calcula la decisión del scorer. El cálculo del motor determinista es
    CONDICIONAL: solo se computa si se cumple una condición necesaria barata
    (el scorer ha mandado a un cap-30 a una recogida pequeña Y queda una
    recogida grande pendiente), sin la cual el guardrail jamás podría disparar.
    Si el guardrail detecta un desperdicio de portador cap-30 (desacuerdo
    scorer vs motor), devuelve la decisión del motor; en cualquier otro caso,
    la del scorer. Sin modelo disponible cae al motor determinista. El
    guardrail se desactiva con GUARDRAIL=0.
    """
    decisiones_scorer = _decidir_scorer(estado)

    # Guardrail desactivado: devolver el scorer tal cual.
    if not GUARDRAIL_HABILITADO:
        return decisiones_scorer

    # Sin modelo (fallback): el scorer no decidió nada → motor determinista.
    if not decisiones_scorer:
        return decidir_motor(estado)

    # Cálculo del motor condicional a la condición necesaria del guardrail.
    if not _scorer_quema_cap30(estado, decisiones_scorer):
        return decisiones_scorer

    decisiones_motor = decidir_motor(estado)
    if _desacuerdo_cap30(estado, decisiones_scorer, decisiones_motor):
        return decisiones_motor
    return decisiones_scorer
