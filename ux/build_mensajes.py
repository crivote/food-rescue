#!/usr/bin/env python3
"""Escribe el mensaje de asignación de cada misión dentro de data/turno.json.

El mensaje es la palanca de motivación del prototipo: la tarjeta de misión
explica al voluntario *por qué* le toca esta recogida, con datos de su propio
turno (lo que lleva hecho, lo que le falta para su insignia). No es texto
escrito a mano: lo genera un LLM a partir de un contexto estructurado.

Mecanismo (el mismo que describe docs/AI_METHODS.md §9.1, aplicado al
itinerario completo en vez de a una decisión suelta):

  1. Se corre el MOTOR real sobre el escenario y se reproduce el turno del
     voluntario tick a tick. Eso da, por misión, los datos que el motor
     computa al decidir pero no exporta (n_cap = cuántos voluntarios podían
     rescatar esa recogida) y el acumulado del turno.
  2. Con eso se construye un CONTEXTO RICO por misión: no solo las raciones
     y la escasez, también lo que el voluntario lleva andado, las entregas
     que ya hizo, el objetivo del turno y los puntos que le faltan para
     subir de nivel.
  3. Un LLM (endpoint OpenAI-compatible) traduce ese contexto a una frase
     cercana. NO interviene en la decisión: el motor sigue siendo
     determinista y autoritario.
  4. El resultado se escribe en el propio `data/turno.json`, y
     `build_turno.py` lo PRESERVA al regenerar la traza.

Uso:
  python3 build_mensajes.py [--voluntario v05] [--escenario sample_01]
                            [--seco]      # solo muestra, no escribe

Configuración (variables de entorno, ninguna credencial hardcodeada):
  LLM_ENDPOINT / LLM_MODEL / LLM_API_KEY

Sin esas variables —o sin red— cada misión cae a una plantilla determinista
que usa los MISMOS datos del contexto. Nunca deja de responder.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
HARNESS = os.path.join(RAIZ, "ai-for-good-72h-harness", "comida")
SOLVER = os.path.join(RAIZ, "solver_match_crit.py")
TURNO = os.path.join(AQUI, "data", "turno.json")

sys.path.insert(0, HARNESS)
sys.path.insert(0, RAIZ)
from simulate import Simulador  # noqa: E402
import solver_match_crit as smc  # noqa: E402

# Niveles del prototipo (gemela de ux/js/gamificacion.js): umbral de puntos.
NIVELES = [(0, "Primeros pasos"), (150, "Colaboración"), (400, "Voluntariado"),
           (900, "Rescate"), (1500, "Líder de turno")]
PTS_POR_RACION = 10

# ---------------------------------------------------------------------------
# Prompt few-shot. Enseña al modelo a usar el contexto RICO —el hito de
# nivel, lo que ya lleva hecho— y a no inventar ni soltar jerga.
# ---------------------------------------------------------------------------
SYSTEM = (
    "Escribes UNA frase (máximo dos) en español para la app de voluntariado "
    "de un banco de alimentos. Se la muestras a la persona voluntaria justo "
    "cuando le llega una misión nueva, y tu frase es lo que la anima a "
    "aceptarla.\n"
    "Reglas:\n"
    "- Habla de tú, con cercanía y sin exagerar. Nada de mayúsculas ni de "
    "signos de admiración repetidos.\n"
    "- Usa como mucho DOS de los datos del contexto, los que más animen a "
    "ESTA persona en ESTE momento: lo que lleva salvado hoy, lo que le falta "
    "para el objetivo del turno o para subir de nivel, si es de las pocas "
    "personas que pueden llegar, o si el margen de tiempo es justo.\n"
    "- Si el contexto lleva progreso del turno (entregas_hechas, "
    "raciones_salvadas_hoy, min_turno_lleva), úsalo: la frase tiene que "
    "sonar a mitad de camino, no a primera misión del día.\n"
    "- Si sube_de_nivel es true, ese es el dato más importante que hay: "
    "es el momento de celebrarlo.\n"
    "- Nunca menciones el sistema, ni el reparto, ni cálculos, ni de dónde "
    "salen las misiones. La persona no sabe que hay un sistema detrás.\n"
    "- No inventes ningún dato que no esté en el contexto ni prometas nada "
    "que no diga el contexto. Si no sabes algo, no lo digas.\n"
    "- Vocabulario prohibido: 'algoritmo', 'sistema', 'asignación', 'ratio', "
    "'optimización', 'capacidad de transporte', 'ruta óptima', 'nodos'.\n"
    "- Devuelve SOLO la frase, sin comillas y sin explicar nada."
)

FEWSHOT = [
    {
        "ctx": {"mision": 2, "misiones_totales": 3, "raciones": 12,
                "min_para_caducar": 38, "min_recorrido": 9,
                "entregas_hechas": 1, "raciones_salvadas_hoy": 15,
                "objetivo_turno": 30, "raciones_para_objetivo": 15,
                "voluntarios_capaces": 4, "sube_de_nivel": False},
        "frase": "Llevas 15 raciones salvadas y con estas 12 te quedas a nada "
                 "del objetivo de hoy. Son 9 minutos de camino, te da tiempo "
                 "de sobra.",
    },
    {
        "ctx": {"mision": 4, "misiones_totales": 4, "raciones": 22,
                "min_para_caducar": 21, "min_recorrido": 5,
                "entregas_hechas": 3, "raciones_salvadas_hoy": 48,
                "objetivo_turno": 50, "raciones_para_objetivo": 0,
                "voluntarios_capaces": 1, "sube_de_nivel": True,
                "nivel_actual": "Voluntariado", "nivel_siguiente": "Rescate"},
        "frase": "Última del turno, y con estas 22 pasas a Rescate. Eres la "
                 "única persona que puede llegar a tiempo a por ellas.",
    },
]


def _mensajes(ctx):
    msgs = [{"role": "system", "content": SYSTEM}]
    for ex in FEWSHOT:
        msgs.append({"role": "user", "content":
                     "Contexto: " + json.dumps(ex["ctx"], ensure_ascii=False)})
        msgs.append({"role": "assistant", "content": ex["frase"]})
    msgs.append({"role": "user", "content":
                 "Contexto: " + json.dumps(ctx, ensure_ascii=False)})
    return msgs


def _config():
    endpoint = os.environ.get("LLM_ENDPOINT", "").strip()
    modelo = os.environ.get("LLM_MODEL", "").strip()
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not (endpoint and modelo and key):
        return None
    return endpoint, modelo, key


def llamar_llm(ctx):
    cfg = _config()
    if cfg is None:
        raise RuntimeError("faltan LLM_ENDPOINT / LLM_MODEL / LLM_API_KEY")
    endpoint, modelo, key = cfg
    body = json.dumps({"model": modelo, "messages": _mensajes(ctx),
                       "max_tokens": 160, "temperature": 0.4}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
    })
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"].strip().strip('"')


# ---------------------------------------------------------------------------
# Contexto rico por misión
# ---------------------------------------------------------------------------

def nivel_de(puntos):
    idx = 0
    for i, (umbral, _) in enumerate(NIVELES):
        if puntos >= umbral:
            idx = i
    return idx


def contexto_mision(i, m, rec, vol, ncap, acumulado_previo, puntos_base,
                    objetivo):
    """Contexto estructurado de la misión `i`, tal como lo ve el voluntario."""
    raciones = m["comidas"]
    puntos_antes = puntos_base + PTS_POR_RACION * acumulado_previo
    puntos_despues = puntos_antes + PTS_POR_RACION * raciones
    niv_antes = nivel_de(puntos_antes)
    niv_despues = nivel_de(puntos_despues)
    umbral_sig = NIVELES[niv_antes + 1][0] if niv_antes + 1 < len(NIVELES) else None

    ctx = {
        "mision": i + 1,
        "misiones_totales": None,          # lo rellena quien llama
        "raciones": raciones,
        "min_para_caducar": int(rec["caduca_min"] - m["min"]),
        "min_recorrido": int(round(m["minutos"])),
        "min_turno_lleva": int(m["min"] - vol["desde_min"]),
        "min_turno_queda": int(vol["hasta_min"] - m["min"]),
        "entregas_hechas": i,
        "raciones_salvadas_hoy": acumulado_previo,
        "objetivo_turno": objetivo,
        "raciones_para_objetivo": max(0, objetivo - acumulado_previo),
        "voluntarios_capaces": ncap,
        "sube_de_nivel": niv_despues > niv_antes,
        "nivel_actual": NIVELES[niv_antes][1],
    }
    if niv_despues > niv_antes:
        ctx["nivel_siguiente"] = NIVELES[niv_despues][1]
    elif umbral_sig is not None:
        # Solo cuando NO se sube de nivel en esta mision. Si se sube, decir
        # "te faltan N" contradice el hito y el modelo se queda con lo
        # pesimista: los dos campos juntos se estorban.
        faltan_pts = max(0, umbral_sig - puntos_antes)
        ctx["raciones_para_subir_nivel"] = -(-faltan_pts // PTS_POR_RACION)
    if objetivo > acumulado_previo:
        ctx["cumple_objetivo_con_esta"] = (
            acumulado_previo + raciones >= objetivo)
    else:
        ctx["objetivo_ya_cumplido"] = True
    return ctx


def fallback(ctx):
    """Plantilla determinista: mismos datos, sin LLM. Nunca deja sin frase.

    Cada rama dice algo que el contexto AFIRMA: nada de "está cerca" sin
    comprobar el recorrido, ni de escasez si hay varios voluntarios capaces.
    """
    rac = ctx["raciones"]
    capaces = ctx.get("voluntarios_capaces", 9)

    if ctx["min_para_caducar"] <= 30:
        motivo = (f"Caducan en {ctx['min_para_caducar']} minutos y solo "
                  f"tienes {ctx['min_recorrido']} de camino")
    elif capaces == 1:
        motivo = (f"Eres la única persona que puede llegar a por estas "
                  f"{rac} raciones")
    elif ctx.get("objetivo_ya_cumplido") and ctx["entregas_hechas"] > 0:
        motivo = (f"Ya llevas {ctx['raciones_salvadas_hoy']} raciones hoy; "
                  f"estas {rac} son otras {ctx['min_recorrido']} de camino")
    elif ctx["entregas_hechas"] > 0:
        motivo = (f"Llevas {ctx['raciones_salvadas_hoy']} raciones salvadas y "
                  f"estas {rac} te acercan al objetivo del turno")
    else:
        motivo = f"Estas {rac} raciones te esperan a {ctx['min_recorrido']} de camino"

    if ctx.get("sube_de_nivel"):
        return f"{motivo}; con esta pasas a {ctx['nivel_siguiente']}."
    if ctx.get("cumple_objetivo_con_esta"):
        return f"{motivo}; y con esta cumples el objetivo de hoy."
    return motivo + "."


def frase(ctx):
    try:
        return llamar_llm(ctx)
    except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError,
            KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"[aviso] LLM no disponible ({e}); uso plantilla determinista.",
              file=sys.stderr)
        return fallback(ctx)


# ---------------------------------------------------------------------------
# Replay del motor: contexto del tick + n_cap real
# ---------------------------------------------------------------------------

def replay(escenario, voluntario):
    """Corre el motor y devuelve (misiones del voluntario, contexto por tick)."""
    esc = json.load(open(escenario, encoding="utf-8"))
    rec = {r["id"]: r for r in esc["recogidas"]}
    vol = {v["id"]: v for v in esc["voluntarios"]}[voluntario]

    sim = Simulador(esc)
    ticks = {}

    def decidir(estado):
        # El motor computa n_cap al decidir (`_criticidad`) pero no lo
        # exporta: se recalcula aquí con su misma función, así el contexto
        # lleva el valor real del tick y no una aproximación.
        ticks[estado["minuto"]] = {
            "ncap": smc._criticidad(estado),
            "libres": sum(1 for v in estado["voluntarios"] if v["activo"]
                          and v["libre_min"] <= estado["minuto"]
                          and v["hasta_min"] > estado["minuto"]),
        }
        return smc.decidir(estado)

    sim.correr(decidir)
    resultado = sim.resultado()
    mias = [e for e in sim.registro
            if e.get("ok") and e.get("voluntario") == voluntario]
    return mias, ticks, rec, vol, esc, resultado


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--voluntario", default="v05")
    p.add_argument("--escenario", default="sample_01")
    p.add_argument("--seco", action="store_true",
                   help="muestra los mensajes sin escribir el json")
    a = p.parse_args()

    escenario = os.path.join(HARNESS, "scenarios", a.escenario + ".json")
    if not os.path.exists(escenario):
        raise SystemExit(f"No existe el escenario {escenario}")
    if not os.path.exists(SOLVER):
        raise SystemExit(f"No encuentro el asignador en {SOLVER}")

    mias, ticks, rec, vol, esc, resultado = replay(escenario, a.voluntario)

    with open(TURNO, encoding="utf-8") as f:
        turno = json.load(f)
    objetivo = turno["objetivo_turno"]
    puntos_base = turno["puntos_base"]

    print(f"escenario : {esc['nombre']} | motor {resultado['porcentaje_salvado']}% "
          f"({resultado['comidas_rescatadas']}/{resultado['comidas_totales']})")
    print(f"voluntario: {a.voluntario} | {len(mias)} misiones | "
          f"cap {vol['capacidad']}\n")

    acumulado = 0
    if not _config():
        print("[aviso] sin LLM_ENDPOINT/LLM_MODEL/LLM_API_KEY: "
              "plantillas deterministas.\n", file=sys.stderr)

    for i, m in enumerate(mias):
        ncap = ticks[m["min"]]["ncap"].get(m["recogida"], 1)
        ctx = contexto_mision(i, m, rec[m["recogida"]], vol, ncap,
                              acumulado, puntos_base, objetivo)
        ctx["misiones_totales"] = len(mias)
        texto = frase(ctx)
        turno["misiones"][i]["mensaje"] = texto
        turno["misiones"][i]["contexto"] = ctx
        acumulado += m["comidas"]
        hito = ("SUBE A " + ctx["nivel_siguiente"] if ctx.get("sube_de_nivel")
                else "cumple objetivo" if ctx.get("cumple_objetivo_con_esta")
                else "")
        print(f"  m{i+1} {m['recogida']:4} {m['comidas']:3}rac  n_cap={ncap}  "
              f"{hito}")
        print(f"      {texto}")

    if a.seco:
        print("\n[seco] no se ha escrito nada")
        return

    with open(TURNO, "w", encoding="utf-8") as f:
        json.dump(turno, f, ensure_ascii=False, indent=2)
    print(f"\nescrito: {os.path.relpath(TURNO, RAIZ)}")


if __name__ == "__main__":
    main()
