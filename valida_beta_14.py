#!/usr/bin/env python3
"""
Validación PAREADA independiente: BETA=1.0 vs BETA=1.4 sobre semillas NUEVAS
(7001..7000+n), fuera de la muestra usada en los barridos (5001..7000).

IMPORTANTE (bug corregido): `decidir` lee BETA como global del módulo, y
`importlib.reload` reutiliza el namespace. Por tanto NO se pueden capturar dos
referencias `dec` por adelantado — hay que hacer reload ANTES de cada simulación
y correrla inmediatamente, para que el global BETA sea el correcto en cada tick.

Mide el delta emparejado (por escenario) de porcentaje_salvado.

Uso: python3 valida_beta_14.py [n] [semilla_inicio]
"""
import importlib
import os
import statistics
import sys

HARNESS = "ai-for-good-72h-harness/comida"
sys.path.insert(0, HARNESS)
from generar_escenario import generar  # noqa: E402
from simulate import Simulador      # noqa: E402

import solver_match_crit as smc  # noqa: E402


def correr(esc, beta):
    """Reload con BETA=beta y corre la simulación INMEDIATAMENTE (global correcto)."""
    prev = os.environ.get("BETA")
    os.environ["BETA"] = str(beta)
    importlib.reload(smc)
    res = Simulador(esc).correr(smc.decidir)["porcentaje_salvado"]
    if prev is None:
        os.environ.pop("BETA", None)
    else:
        os.environ["BETA"] = prev
    return res


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    ini = int(sys.argv[2]) if len(sys.argv) > 2 else 7001
    escs = [generar(s) for s in range(ini, ini + n)]

    s10 = [correr(e, 1.0) for e in escs]
    s14 = [correr(e, 1.4) for e in escs]

    deltas = [b - a for a, b in zip(s10, s14)]
    m = statistics.mean(deltas)
    sd = statistics.pstdev(deltas)
    se = sd / (n ** 0.5)

    ganan = sum(1 for d in deltas if d > 0.01)
    pierden = sum(1 for d in deltas if d < -0.01)
    empatan = n - ganan - pierden

    print(f"n={n} semillas NUEVAS ({ini}..{ini+n-1})\n")
    print(f"media BETA=1.0 : {statistics.mean(s10):.2f}%")
    print(f"media BETA=1.4 : {statistics.mean(s14):.2f}%")
    print(f"\ndelta emparejado (1.4 - 1.0):")
    print(f"  media = {m:+.3f} pts  (se = {se:.3f}, IC95 = [{m-1.96*se:+.3f}, {m+1.96*se:+.3f}])")
    print(f"  1.4 gana en {ganan}/{n}  ({100*ganan/n:.1f}%)")
    print(f"  1.4 pierde en {pierden}/{n}  ({100*pierden/n:.1f}%)")
    print(f"  empate en {empatan}/{n}")
    print(f"\npeor caso emparejado:")
    print(f"  min BETA=1.0 : {min(s10):.1f}%")
    print(f"  min BETA=1.4 : {min(s14):.1f}%")
    print(f"  min delta    : {min(deltas):+.1f} pts")


if __name__ == "__main__":
    main()
