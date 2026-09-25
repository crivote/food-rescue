#!/usr/bin/env python3
# ── SOLVER PRINCIPAL (LA ENTREGA) ──────────────────────────────────────
# NextFood — solucionador unificado: scorer LightGBM (aprendizaje por
# imitación) + guardrail determinista cap-30. Este fichero es el punto de
# entrada que hay que ejecutar. Reexporta `decidir` de ml/solver_scorer.py,
# que es donde vive el método real; aquí solo se resuelve el import.
#
#   python3 ai-for-good-72h-harness/comida/simulate.py \
#       --scenario ai-for-good-72h-harness/comida/scenarios/sample_01.json \
#       --solver solve.py
#
# Devuelve 58.5% (453 raciones) en el escenario publicado.
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "ml"))

from solver_scorer import decidir  # noqa: E402,F401

__all__ = ["decidir"]
