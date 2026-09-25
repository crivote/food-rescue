#!/usr/bin/env python3
"""
Etiquetado nocturno: genera escenarios, resuelve el óptimo exacto (CP-SAT) y
guarda el PLAN por semilla en un JSONL resumible.

Fuente de verdad para el behavioral cloning de mañana: el plan óptimo es
independiente de cómo se derive la etiqueta (estado -> decisión) después.
Esta noche solo se materializa el plan, que es lo caro (CPU-bound).

Uso:
  python3 etiquetar_cpsat.py --desde 20000 --hasta 20399 --tope 45 --salida labels/planes.jsonl

Resumen: si el proceso muere a mitad, al re-lanzar salta las semillas ya
presentes en el JSONL (resume). Cada línea es un JSON con:
  {"semilla", "status", "wall", "resc", "total", "pct", "gap", "plan": [...]}
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "ai-for-good-72h-harness", "comida"))

from generar_escenario import generar          # noqa: E402
from optimo_exacto import resolver             # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--desde", type=int, default=20000)
    p.add_argument("--hasta", type=int, default=20399)
    p.add_argument("--tope", type=float, default=45.0,
                   help="max_seconds por escenario")
    p.add_argument("--salida", default=os.path.join(RAIZ, "labels", "planes.jsonl"))
    a = p.parse_args()

    out_dir = os.path.dirname(a.salida)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # resume: semillas ya presentes en el fichero
    ya_hechas = set()
    if os.path.exists(a.salida):
        with open(a.salida) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ya_hechas.add(json.loads(line)["semilla"])
                except (json.JSONDecodeError, KeyError):
                    continue

    semillas = [s for s in range(a.desde, a.hasta + 1) if s not in ya_hechas]
    print(f"[etiquetar] desde={a.desde} hasta={a.hasta} "
          f"tope={a.tope}s salida={a.salida}", flush=True)
    print(f"[etiquetar] pendientes={len(semillas)} "
          f"(ya hechas={len(ya_hechas)})", flush=True)

    t0 = time.time()
    n_opt = 0
    n_feas = 0
    n_unk = 0
    tiempos = []

    for i, s in enumerate(semillas, 1):
        esc = generar(s)
        status, resc, total, pct, nvars, plan, wall, gap, bound = \
            resolver(esc, a.tope, con_cancelaciones=True)

        # plan -> serializable (origen None se mantiene como None)
        plan_ser = [[vid, t, rid, cid, com, origen] for
                    (vid, t, rid, cid, com, origen) in plan]

        registro = {
            "semilla": s,
            "status": status,
            "wall": round(wall, 2),
            "resc": int(round(resc)),
            "total": int(total),
            "pct": round(pct, 2),
            "gap": (None if gap is None else round(gap, 2)),
            "nvars": int(nvars),
            "plan": plan_ser,
        }

        with open(a.salida, "a") as f:
            f.write(json.dumps(registro) + "\n")
            f.flush()

        if status == "OPTIMAL":
            n_opt += 1
        elif status == "FEASIBLE":
            n_feas += 1
        else:
            n_unk += 1
        tiempos.append(wall)

        if i % 10 == 0 or i == len(semillas):
            el = time.time() - t0
            media = sum(tiempos) / len(tiempos)
            mediana = sorted(tiempos)[len(tiempos) // 2]
            print(f"[{i}/{len(semillas)}] OPTIMAL={n_opt} FEASIBLE={n_feas} "
                  f"OTROS={n_unk} | media={media:.1f}s mediana={mediana:.1f}s "
                  f"max={max(tiempos):.1f}s | elapsed={el:.0f}s", flush=True)

    el = time.time() - t0
    print(f"[FIN] {len(semillas)} semillas en {el:.0f}s "
          f"({el/len(semillas):.1f}s/semilla) "
          f"| OPTIMAL={n_opt} ({100*n_opt/len(semillas):.0f}%) "
          f"FEASIBLE={n_feas} OTROS={n_unk}", flush=True)


if __name__ == "__main__":
    main()
