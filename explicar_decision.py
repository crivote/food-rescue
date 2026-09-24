#!/usr/bin/env python3
"""
Explicación en lenguaje natural de una decisión del motor.

El motor (solver_match_crit.py) emite asignaciones {voluntario, recogida, centro}
que nacen de un contexto de decisión estructurado. Este script toma ESE contexto
(los mismos campos que el motor computa) y lo traduce a una frase corta, cercana
y sin jerga técnica, dirigida al voluntario.

Mecanismo (propuesta "transparencia al usuario final", no XAI post-hoc):
  1. El motor expone un contexto JSON de la decisión (raciones + escasez + plazo).
  2. Este script lo mete en un prompt few-shot con ejemplos.
  3. Un LLM barato (cualquier endpoint OpenAI-compatible) genera la frase natural.

No interviene en la decisión: el motor sigue siendo determinista y autoritario.
Esto solo convierte su salida en algo que un humano entiende.

Uso:
  python3 explicar_decision.py                  # usa el ejemplo embebido
  python3 explicar_decision.py --json ctx.json  # contexto real desde el motor

Configuración (variables de entorno, ninguna hardcodeada):
  LLM_ENDPOINT  — endpoint OpenAI-compatible /chat/completions
  LLM_MODEL     — nombre del modelo
  LLM_API_KEY   — clave de autenticación (Bearer)

Si falta cualquiera de las tres, o no hay red, imprime un fallback determinista
(plantilla) en stderr y sigue respondiendo. Nunca deja de responder.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Prompt few-shot: enseña al modelo a traducir "factores de decisión" a
# lenguaje natural, en español, en una sola frase, sin jerga técnica.
# ---------------------------------------------------------------------------
SYSTEM = (
    "Eres un asistente que escribe una frase de UNA línea en español para "
    "explicar a un voluntario por qué se le ha asignado una recogida de comida. "
    "La frase debe ser cercana, sin jerga técnica, y mencionar SOLO los datos "
    "que aparecen en el contexto (raciones, capacidad, cuántos voluntarios "
    "podían hacerlo, cuánto falta para que caduque). No inventes nada. "
    "No uses palabras como 'ratio', 'peso', 'algoritmo', 'feature', 'n_cap'."
)

FEWSHOT = [
    {
        "ctx": {"raciones": 30, "capacidad_voluntario": 30,
                "voluntarios_capaces": 1, "min_para_caducar": 45},
        "frase": "Por tu capacidad de transporte (puedes llevar hasta 30 "
                 "raciones), eres el único voluntario que puede recoger esta "
                 "donación importante antes de que caduque. ¡Contamos contigo!",
    },
    {
        "ctx": {"raciones": 18, "capacidad_voluntario": 25,
                "voluntarios_capaces": 3, "min_para_caducar": 20},
        "frase": "Esta recogida de 18 raciones está a punto de caducar y tú "
                 "puedes llegar a tiempo; hay otros dos voluntarios ocupados, "
                 "así que te toca a ti.",
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
    """Lee endpoint, modelo y clave del entorno. Devuelve None si falta algo."""
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
                       "max_tokens": 120, "temperature": 0.2}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"].strip()


def fallback(ctx):
    """Plantilla determinista por si no hay red, clave o configuración."""
    rac = ctx["raciones"]
    cap = ctx["capacidad_voluntario"]
    ncap = ctx.get("voluntarios_capaces", 1)
    plazo = ctx.get("min_para_caducar", 0)
    if ncap == 1 and rac >= cap * 0.8:
        return (f"Por tu capacidad de transporte (puedes llevar hasta {cap} "
                f"raciones), eres el único voluntario que puede recoger esta "
                f"donación de {rac} raciones antes de que caduque. ¡Contamos contigo!")
    return (f"Esta recogida de {rac} raciones caduca en {plazo} min y tú "
            f"puedes llegar a tiempo.")


def explicar(ctx):
    try:
        return llamar_llm(ctx)
    except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError,
            KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"[aviso] LLM no disponible ({e}); uso plantilla determinista.",
              file=sys.stderr)
        return fallback(ctx)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", help="fichero con el contexto JSON de la decisión")
    args = p.parse_args()

    if args.json:
        with open(args.json, encoding="utf-8") as f:
            ctx = json.load(f)
    else:
        # Ejemplo embebido: la asignación real v05 → r25 (30 raciones, único
        # portador cap-30 libre a tiempo). Contexto que el motor computa.
        ctx = {
            "raciones": 30,
            "capacidad_voluntario": 30,
            "voluntarios_capaces": 1,
            "min_para_caducar": 45,
        }

    print(explicar(ctx))


if __name__ == "__main__":
    main()
