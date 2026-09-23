#!/usr/bin/env python3
"""
Estratificación por cuartiles de dificultad estructural (INDEPENDIENTE del solver).

Índice de dificultad compuesto por las dos features estructurales dominantes
(ver firma_global.py, pearson más alto tras alcanzable_pct):
    dificultad = -z(alcanzable_pct) + z(comida_grande_por_cap30) + 0.5*z(d_rec_centro_media)
  (z = z-score sobre la muestra; alcanzable_pct alto = fácil -> signo negativo)

Particiona la muestra en 4 cuartiles (Q1 fácil ... Q4 difícil) y mide, en cada
uno, el greedy del concurso y el motor final. Responde: "¿cómo se comporta mi
motor en los escenarios que un jurado cabrón elegiría?" — sin sesgo, porque la
estratificación es por estructura, no por resultado del matcher.

Uso: python3 estratifica_cuartiles.py [n] [semilla_inicio]
"""
import importlib.util
import json
import statistics
import sys

HARNESS = "ai-for-good-72h-harness/comida"
sys.path.insert(0, HARNESS)
from generar_escenario import generar  # noqa: E402
from simulate import Simulador, km   # noqa: E402

# reusa la firma global
import firma_global as fg  # noqa: E402


def cargar(ruta):
    spec = importlib.util.spec_from_file_location("solver", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.decidir


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    ini = int(sys.argv[2]) if len(sys.argv) > 2 else 5001

    greedy = cargar(f"{HARNESS}/baseline_greedy.py")
    base = cargar("solver_match.py")        # matcher base (comidas/min, la ref. de la doc)
    crit = cargar("solver_match_crit.py")   # motor final

    # generar + firmar + score de dificultad
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

    # ordenar y partir en 4 cuartiles iguales (n//4 cada uno)
    idx = sorted(range(n), key=lambda i: dificultad[i])
    qs = [idx[i * n // 4:(i + 1) * n // 4] for i in range(4)]

    print(f"muestra: {n} semillas ({ini}..{ini+n-1})\n")
    print(f"{'cuartil':>8s} {'n':>4s} {'greedy':>8s} {'base':>7s} {'motor':>7s} "
          f"{'gap_vs_base':>11s} {'alc_medio':>9s} {'cg_cap30':>8s}")
    for qi, q in enumerate(qs, 1):
        g_vals = [Simulador(escs[i]).correr(greedy)["porcentaje_salvado"] for i in q]
        b_vals = [Simulador(escs[i]).correr(base)["porcentaje_salvado"] for i in q]
        c_vals = [Simulador(escs[i]).correr(crit)["porcentaje_salvado"] for i in q]
        g_mean = statistics.mean(g_vals)
        b_mean = statistics.mean(b_vals)
        c_mean = statistics.mean(c_vals)
        alc = statistics.mean([firmas[i]["alcanzable_pct"] for i in q])
        cg = statistics.mean([firmas[i]["comida_grande_por_cap30"] for i in q])
        print(f"  Q{qi}    {len(q):4d} {g_mean:7.1f}% {b_mean:6.1f}% {c_mean:6.1f}% "
              f"{c_mean - b_mean:+10.1f} {alc:8.1f}% {cg:8.1f}")

    # desglose del cuartil más difícil (Q4)
    q4 = qs[3]
    g4 = [Simulador(escs[i]).correr(greedy)["porcentaje_salvado"] for i in q4]
    b4 = [Simulador(escs[i]).correr(base)["porcentaje_salvado"] for i in q4]
    c4 = [Simulador(escs[i]).correr(crit)["porcentaje_salvado"] for i in q4]
    print("\n=== CUARTIL MÁS DIFÍCIL (Q4) ===")
    print(f"greedy : media {statistics.mean(g4):.1f}  min {min(g4):.1f}  "
          f"max {max(g4):.1f}  std {statistics.pstdev(g4):.1f}")
    print(f"base   : media {statistics.mean(b4):.1f}  min {min(b4):.1f}  "
          f"max {max(b4):.1f}  std {statistics.pstdev(b4):.1f}")
    print(f"motor  : media {statistics.mean(c4):.1f}  min {min(c4):.1f}  "
          f"max {max(c4):.1f}  std {statistics.pstdev(c4):.1f}")
    d4 = [c - b for c, b in zip(c4, b4)]
    print(f"gap_vs_base : media {statistics.mean(d4):+.1f}  "
          f"(motor gana en {sum(1 for d in d4 if d > 0)}/{len(d4)})")


if __name__ == "__main__":
    main()
