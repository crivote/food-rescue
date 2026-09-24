#!/usr/bin/env python3
"""
Benchmark estratificado motor vs scorer aprendido, a gran escala, fuera de muestra.

Responde la pregunta de diseño del scorer: "¿es una alternativa BARATA y MEJOR
al motor determinista, sin ejecutar el solver pesado en runtime?"

Metodología (hereda de estratifica_cuartiles.py y firma_global.py):
  - Genera N semillas fuera del rango de entrenamiento (20300-20899).
  - Firma estructural independiente del solver (firma_global.firma).
  - Índice de dificultad compuesto (misma fórmula que estratifica_cuartiles):
        dificultad = -z(alcanzable_pct) + z(comida_grande_por_cap30)
                     + 0.5*z(d_rec_centro_media)
  - Particiona en 4 cuartiles (Q1 fácil ... Q4 difícil).
  - En cada cuartil mide motor vs scorer (media, min, max, nº de victorias).

Uso:
  python3 bench_estratificado.py [n] [semilla_inicio] [--modelo ruta]
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import solver_match_crit as smc  # noqa: E402
import solver_scorer as ss  # noqa: E402
import firma_global as fg  # noqa: E402

TRAIN_LO = 20300
TRAIN_HI = 20899


def _out_of_sample_range(ini, n):
    """Asegura que el rango no pisa el de entrenamiento."""
    rng = list(range(ini, ini + n))
    # si colisiona, desplaza más allá del training
    if any(TRAIN_LO <= s <= TRAIN_HI for s in rng):
        raise SystemExit(
            f"rango {ini}..{ini+n-1} pisa el set de entrenamiento "
            f"{TRAIN_LO}..{TRAIN_HI}; usa otro semilla_inicio")
    return rng


def main():
    p = argparse.ArgumentParser()
    p.add_argument("n", type=int, nargs="?", default=1200)
    p.add_argument("ini", type=int, nargs="?", default=5001)
    p.add_argument("--modelo", default="/tmp/scorer_variantes/scorer_binario.txt")
    a = p.parse_args()

    semillas = _out_of_sample_range(a.ini, a.n)
    os.environ["SCORER_MODEL"] = a.modelo
    ss._modelo = None
    print(f"[bench] {a.n} semillas fuera de muestra ({semillas[0]}..{semillas[-1]})",
          flush=True)
    print(f"[bench] modelo: {a.modelo}", flush=True)

    # generar + firmar + índice de dificultad
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

    print(f"\n{'cuartil':>8s} {'n':>5s} {'motor':>8s} {'scorer':>8s} "
          f"{'delta':>8s} {'gana_scorer':>11s} {'alc_medio':>9s} {'cg_cap30':>8s}",
          flush=True)

    total_m, total_s = 0.0, 0.0
    total_gana = 0
    for qi, q in enumerate(qs, 1):
        m_vals, s_vals = [], []
        for i in q:
            esc = escs[i]
            r1 = Simulador(copy.deepcopy(esc)).correr(smc.decidir)
            r2 = Simulador(copy.deepcopy(esc)).correr(ss.decidir)
            m_vals.append(r1["porcentaje_salvado"])
            s_vals.append(r2["porcentaje_salvado"])
        m_mean = statistics.mean(m_vals)
        s_mean = statistics.mean(s_vals)
        gana = sum(1 for m, s in zip(m_vals, s_vals) if s > m)
        alc = statistics.mean([firmas[i]["alcanzable_pct"] for i in q])
        cg = statistics.mean([firmas[i]["comida_grande_por_cap30"] for i in q])
        print(f"  Q{qi}    {len(q):5d} {m_mean:7.2f}% {s_mean:7.2f}% "
              f"{s_mean - m_mean:+7.2f} {gana:5d}/{len(q)} "
              f"{alc:8.1f}% {cg:8.1f}", flush=True)
        total_m += sum(m_vals)
        total_s += sum(s_vals)
        total_gana += gana

    print(f"\n=== TOTAL (n={a.n}) ===")
    print(f"motor  : {total_m/a.n:.2f}%")
    print(f"scorer : {total_s/a.n:.2f}%")
    print(f"delta  : {total_s/a.n - total_m/a.n:+.2f} pts")
    print(f"scorer gana: {total_gana}/{a.n} "
          f"({100*total_gana/a.n:.1f}%)")


if __name__ == "__main__":
    main()
