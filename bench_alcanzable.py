#!/usr/bin/env python3
"""
Techo alcanzable + normalización de scores.

Dos límites superiores del % rescatable, ambos independientes de cualquier
solver (pura física/estructura):

  (1) TECHO POR-ÍTEM (reachability): comidas que algún voluntario puede
      rescatar DESDE SU CASA (posición inicial) antes de caducar, entregando
      en un centro abierto y dentro de su ventana. IGNORA la contención
      (que el mismo voluntario no puede hacer todos los viajes). Es un límite
      superior HOLGADO. Validado: sample_01 -> 96.1% (solo r36 inalcanzable).

  (2) TECHO DE CAPACIDAD (capacity/multi-trip): comidas rescatables teniendo
      en cuenta que cada voluntario tiene un nº finito de viajes (cota por
      capacidad y por tiempo). Aproximación LP-relaxada: asignación máxima de
      comidas a voluntarios respetando (a) capacidad por viaje, (b) un máximo
      de viajes por voluntario estimado por su ventana / tiempo medio de viaje.
      Más apretado que (1), aún un límite superior (relaja secuenciación exacta).

Reporta para greedy / matcher-base / matcher-crit:
  - % sobre TOTAL (métrica oficial del harness)
  - % sobre TECHO POR-ÍTEM   (cuán cerca del máximo estructural)
  - % sobre TECHO CAPACIDAD  (cuán cerca del máximo realista)

Uso: python3 bench_alcanzable.py [n] [semilla_inicio]
"""
import importlib.util
import math
import statistics
import sys

HARNESS = "ai-for-good-72h-harness/comida"
sys.path.insert(0, HARNESS)
from generar_escenario import generar  # noqa: E402
from simulate import Simulador, km   # noqa: E402


def cargar(ruta):
    spec = importlib.util.spec_from_file_location("solver", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.decidir


# ── techo (1): reachability por-ítem ──────────────────────────────────────
def _puede_desde_casa(v, r, centros):
    """¿Puede v rescatar r desde su posición inicial (casa) antes de caducar?"""
    if r["comidas"] > v["capacidad"]:
        return False
    t = km(v["pos"], r["pos"]) / v["velocidad_kmh"] * 60
    llega_r = v["desde_min"] + t
    if llega_r > r["caduca_min"]:
        return False
    for c in centros:
        llega_c = llega_r + km(r["pos"], c["pos"]) / v["velocidad_kmh"] * 60
        if llega_c <= c["cierra_min"] and llega_c <= v["hasta_min"]:
            return True
    return False


def techo_por_item(esc):
    vols, recs, cens = esc["voluntarios"], esc["recogidas"], esc["centros"]
    rescatable = 0
    total = 0
    for r in recs:
        total += r["comidas"]
        if any(_puede_desde_casa(v, r, cens) for v in vols):
            rescatable += r["comidas"]
    return rescatable, total


# ── techo (2): capacidad multi-viaje (relajado) ──────────────────────────
def techo_capacidad(esc):
    """Cota superior por capacidad y nº de viajes por voluntario (relajada).

    Cota superior VÁLIDA: ningún plan puede rescatar más comidas que la suma,
    sobre voluntarios, de (nº máximo de viajes) × (capacidad por viaje).
    El nº máximo de viajes se estima con el tiempo de viaje MÍNIMO posible
    para cada voluntario (la recogida más cercana alcanzable + su centro más
    cercano), que es lo que permite el máximo nº de viajes -> cota por arriba.
    Luego se cruza con el techo por-ítem (no puedes rescatar lo inalcanzable)."""
    vols, recs, cens = esc["voluntarios"], esc["recogidas"], esc["centros"]

    # tiempo mínimo de un viaje para cada voluntario (ida + vuelta a centro)
    capacidad_total = 0
    for v in vols:
        t_min = float("inf")
        for r in recs:
            if r["comidas"] > v["capacidad"]:
                continue
            d_centro = min(km(r["pos"], c["pos"]) for c in cens)
            # primer viaje desde casa; siguientes desde el centro más cercano.
            # cota superior: usar el origen más favorable (el que da menos tiempo).
            t_ida_casa = km(v["pos"], r["pos"]) / v["velocidad_kmh"] * 60
            t_ida_centro = d_centro / v["velocidad_kmh"] * 60
            t_vuelta = d_centro / v["velocidad_kmh"] * 60
            # origen óptimo = el que minimiza ida (casa o el centro más cercano)
            t = min(t_ida_casa, t_ida_centro) + t_vuelta
            t_min = min(t_min, t)
        if t_min == float("inf"):
            continue
        ventana = v["hasta_min"] - v["desde_min"]
        k = max(1, int(ventana / t_min))          # nº máximo de viajes
        capacidad_total += k * v["capacidad"]

    # cruce con el techo por-ítem: no se puede rescatar lo inalcanzable
    rescatable_item, total = techo_por_item(esc)
    return min(capacidad_total, rescatable_item), total


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    ini = int(sys.argv[2]) if len(sys.argv) > 2 else 5001

    greedy = cargar(f"{HARNESS}/baseline_greedy.py")
    match = cargar("solver_match.py")
    crit = cargar("solver_match_crit.py")

    # acumuladores: % total, % por-ítem, % capacidad, y los techos
    solvers = {
        "greedy": {"tot": [], "item": [], "cap": []},
        "matcher": {"tot": [], "item": [], "cap": []},
        "crit": {"tot": [], "item": [], "cap": []},
    }
    techos_item = []   # % alcanzable por-ítem por escenario
    techos_cap = []    # % alcanzable por capacidad por escenario

    for s in range(ini, ini + n):
        esc = generar(s)
        r_item, total = techo_por_item(esc)
        r_cap, _ = techo_capacidad(esc)
        techos_item.append(100 * r_item / total)
        techos_cap.append(100 * r_cap / total)

        for key, dec in (("greedy", greedy), ("matcher", match), ("crit", crit)):
            r = Simulador(esc).correr(dec)
            pct = r["porcentaje_salvado"]
            rescatadas = pct * total / 100
            solvers[key]["tot"].append(pct)
            solvers[key]["item"].append(100 * rescatadas / r_item if r_item else 0.0)
            solvers[key]["cap"].append(100 * rescatadas / r_cap if r_cap else 0.0)

    def res(nombre, xs):
        return (f"{nombre:10s} media {statistics.mean(xs):6.1f}  "
                f"min {min(xs):6.1f}  max {max(xs):6.1f}  std {statistics.pstdev(xs):5.1f}")

    print(f"muestra: {n} semillas ({ini}..{ini+n-1})\n")
    print("=== TECHOS (cotas superiores) ===")
    print(res("por-ítem", techos_item))
    print(res("capacidad", techos_cap))
    print()

    for metrica, label in (("tot", "% sobre TOTAL (oficial)"),
                           ("item", "% sobre TECHO por-ítem"),
                           ("cap", "% sobre TECHO capacidad")):
        print(f"=== {label} ===")
        for key in ("greedy", "matcher", "crit"):
            print(res(key, solvers[key][metrica]))
        print()


if __name__ == "__main__":
    main()
