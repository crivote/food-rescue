#!/usr/bin/env python3
"""
Benchmark final: greedy vs matcher base vs motor vs modelo INTEGRADO (scorer +
guardrail cap-30), sobre el MISMO set de escenarios que la tabla principal del
README (2000 semillas 5001..7000), estratificado en cuartiles de dificultad.

Reproduce exactamente la metodología de estratifica_cuartiles.py (índice de
dificultad estructural independiente del solver) y añade la columna del modelo
integrado.

Uso:
  python3 bench_final_integrado.py [n] [semilla_inicio] [--modelo ruta]
"""
import argparse
import copy
import os
import statistics
import sys

HARNESS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "ai-for-good-72h-harness", "comida")
sys.path.insert(0, HARNESS)
from generar_escenario import generar  # noqa: E402
from simulate import Simulador  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import solver_match_crit as smc  # noqa: E402
import solver_scorer as ss  # noqa: E402
import firma_global as fg  # noqa: E402

TRAIN_LO = 20300
TRAIN_HI = 20899


def cargar(ruta):
    import importlib.util
    spec = importlib.util.spec_from_file_location("solver", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.decidir


def main():
    p = argparse.ArgumentParser()
    p.add_argument("n", type=int, nargs="?", default=2000)
    p.add_argument("ini", type=int, nargs="?", default=5001)
    p.add_argument("--modelo", default="models/scorer_full.txt")
    a = p.parse_args()

    semillas = list(range(a.ini, a.ini + a.n))
    if any(TRAIN_LO <= s <= TRAIN_HI for s in semillas):
        raise SystemExit("rango pisa el set de entrenamiento")

    os.environ["SCORER_MODEL"] = a.modelo
    ss._modelo = None

    greedy = cargar(os.path.join(RAIZ, HARNESS, "baseline_greedy.py"))
    base = cargar(os.path.join(RAIZ, "solver_match.py"))
    motor = smc.decidir
    integrado = ss.decidir  # scorer + guardrail cap-30

    print(f"[final] {a.n} semillas ({semillas[0]}..{semillas[-1]}), "
          f"modelo={a.modelo}", flush=True)

    escs = [generar(s) for s in semillas]
    firmas = [fg.firma(e) for e in escs]

    def z(vals):
        m = sum(vals) / len(vals)
        sd = (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5
        return [(x - m) / sd if sd else 0.0 for x in vals]

    z_alc = z([f["alcanzable_pct"] for f in firmas])
    z_cg = z([f["comida_grande_por_cap30"] for f in firmas])
    z_dr = z([f["d_rec_centro_media"] for f in firmas])
    dificultad = [-aa + c + 0.5 * d for aa, c, d in zip(z_alc, z_cg, z_dr)]

    idx = sorted(range(a.n), key=lambda i: dificultad[i])
    qs = [idx[i * a.n // 4:(i + 1) * a.n // 4] for i in range(4)]

    print(f"\n{'cuartil':>8s} {'n':>5s} {'greedy':>7s} {'base':>7s} "
          f"{'motor':>7s} {'integrado':>9s} {'Δ vs motor':>10s}", flush=True)

    tot = {"greedy": 0.0, "base": 0.0, "motor": 0.0, "integrado": 0.0}
    ganador_integrado = 0
    for qi, q in enumerate(qs, 1):
        g, b, m, it = [], [], [], []
        for i in q:
            esc = escs[i]
            g.append(Simulador(copy.deepcopy(esc)).correr(greedy)["porcentaje_salvado"])
            b.append(Simulador(copy.deepcopy(esc)).correr(base)["porcentaje_salvado"])
            m.append(Simulador(copy.deepcopy(esc)).correr(motor)["porcentaje_salvado"])
            it.append(Simulador(copy.deepcopy(esc)).correr(integrado)["porcentaje_salvado"])
        gm = statistics.mean(g)
        bm = statistics.mean(b)
        mm = statistics.mean(m)
        im = statistics.mean(it)
        ganador_integrado += sum(1 for mm_, it_ in zip(m, it) if it_ > mm_)
        print(f"  Q{qi}    {len(q):5d} {gm:6.1f}% {bm:6.1f}% {mm:6.1f}% "
              f"{im:8.1f}% {im - mm:+9.2f}", flush=True)
        tot["greedy"] += sum(g)
        tot["base"] += sum(b)
        tot["motor"] += sum(m)
        tot["integrado"] += sum(it)

    print(f"\n=== TOTAL (n={a.n}) ===")
    for k in ("greedy", "base", "motor", "integrado"):
        print(f"  {k:>9s}: {tot[k]/a.n:.2f}%")
    print(f"  Δ integrado vs motor: {tot['integrado']/a.n - tot['motor']/a.n:+.2f} pts")
    print(f"  integrado gana al motor: {ganador_integrado}/{a.n} "
          f"({100*ganador_integrado/a.n:.1f}%)")


if __name__ == "__main__":
    main()
