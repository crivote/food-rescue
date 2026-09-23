#!/usr/bin/env python3
"""
Simulador de eventos discretos para el reto de comida.

Contrato con tu sistema
-----------------------
El simulador manda eventos y espera decisiones. Tu asignador puede ser:

  · un módulo Python con una función `decidir(estado, evento) -> list[dict]`
  · un ejecutable que lee un JSON por stdin y escribe un JSON por stdout
  · un servidor HTTP con POST /decidir

Los tres reciben lo mismo y devuelven lo mismo, así que el idioma en el que
escribas da igual. Está documentado entero en format.md.

Una decisión es una asignación:

    {"voluntario": "v03", "recogida": "r17", "centro": "c1"}

El simulador la valida contra la física del escenario —el voluntario tiene
que llegar antes de que caduque, el centro tiene que estar abierto cuando
llegue, y la carga tiene que caber— y la ejecuta o la rechaza. Rechazar no
penaliza: lo que penaliza es que la comida se pierda.

Por qué así y no "devuélveme un plan"
-------------------------------------
Porque a las 19:40 cancelan dos voluntarios. Un plan calculado a las 19:00 y
ejecutado a ciegas no es el problema que tienen los bancos de alimentos: el
problema es replantearse con la mitad de la gente y la comida ya caducando.

La métrica
----------
Manda `porcentaje_salvado`. `comidas_por_hora` solo desempata.

Fue al revés, y se ganaba por el denominador: un asignador que hace una sola
recogida cercana y se para saca casi tres veces las comidas por hora del
greedy dejando que se pierda más del 95 % de la comida. Una división premia
trabajar poco; lo que se le pide a un banco de alimentos es que no se pierda
la comida, y el tiempo de voluntario decide entre dos que salvan lo mismo.
"""
import argparse
import importlib.util
import json
import math
import subprocess
import sys


def km(a, b):
    R = 6371.0
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


class Simulador:
    def __init__(self, escenario):
        self.esc = escenario
        self.recogidas = {r["id"]: dict(r) for r in escenario["recogidas"]}
        self.voluntarios = {v["id"]: dict(v) for v in escenario["voluntarios"]}
        self.centros = {c["id"]: dict(c) for c in escenario["centros"]}

        for v in self.voluntarios.values():
            v["libre_min"] = v["desde_min"]
            v["pos_actual"] = list(v["pos"])
            v["minutos_usados"] = 0
            v["activo"] = True

        for r in self.recogidas.values():
            r["asignada"] = False
            r["rescatada"] = False

        self.canceladas = {c["voluntario"]: c["min"] for c in escenario["cancelaciones"]}
        self.registro = []

    # ── estado que ve tu sistema ────────────────────────────────────────
    def estado(self, minuto):
        return {
            "minuto": minuto,
            "recogidas": [
                {
                    "id": r["id"], "pos": r["pos"], "comidas": r["comidas"],
                    "caduca_min": r["caduca_min"], "asignada": r["asignada"],
                    "rescatada": r["rescatada"],
                }
                for r in self.recogidas.values()
            ],
            "voluntarios": [
                {
                    "id": v["id"], "pos": v["pos_actual"], "libre_min": v["libre_min"],
                    "hasta_min": v["hasta_min"], "velocidad_kmh": v["velocidad_kmh"],
                    "capacidad": v["capacidad"], "activo": v["activo"],
                }
                for v in self.voluntarios.values()
            ],
            "centros": [
                {"id": c["id"], "pos": c["pos"], "cierra_min": c["cierra_min"]}
                for c in self.centros.values()
            ],
        }

    # ── ejecución de una decisión ───────────────────────────────────────
    def aplicar(self, minuto, decision):
        v = self.voluntarios.get(decision.get("voluntario"))
        r = self.recogidas.get(decision.get("recogida"))
        c = self.centros.get(decision.get("centro"))

        if not v or not r or not c:
            return self._no("referencia inexistente", decision)
        if not v["activo"]:
            return self._no("voluntario cancelado", decision)
        if r["asignada"]:
            return self._no("recogida ya asignada", decision)
        if r["comidas"] > v["capacidad"]:
            return self._no("no le cabe", decision)

        salida = max(minuto, v["libre_min"])
        a_recogida = km(v["pos_actual"], r["pos"]) / v["velocidad_kmh"] * 60
        llega_recogida = salida + a_recogida

        if llega_recogida > r["caduca_min"]:
            return self._no("llega tarde: ya ha caducado", decision)

        a_centro = km(r["pos"], c["pos"]) / v["velocidad_kmh"] * 60
        llega_centro = llega_recogida + a_centro

        if llega_centro > c["cierra_min"]:
            return self._no("el centro ya ha cerrado", decision)
        if llega_centro > v["hasta_min"]:
            return self._no("se sale de su ventana", decision)

        # Válida: se ejecuta.
        r["asignada"] = True
        r["rescatada"] = True
        v["libre_min"] = llega_centro
        v["pos_actual"] = list(c["pos"])
        v["minutos_usados"] += llega_centro - salida

        self.registro.append({
            "min": round(minuto, 1), "ok": True, "voluntario": v["id"],
            "recogida": r["id"], "centro": c["id"], "comidas": r["comidas"],
            "minutos": round(llega_centro - salida, 1),
        })
        return True

    def _no(self, motivo, decision):
        self.registro.append({"ok": False, "motivo": motivo, "decision": decision})
        return False

    # ── bucle ───────────────────────────────────────────────────────────
    def correr(self, decidir):
        """Un tic cada 5 minutos. Suficiente para un problema de 3 horas."""
        for minuto in range(self.esc["apertura_min"], self.esc["cierre_min"] + 1, 5):
            for vid, cuando in self.canceladas.items():
                if minuto >= cuando and self.voluntarios[vid]["activo"]:
                    self.voluntarios[vid]["activo"] = False
                    self.registro.append({"min": minuto, "evento": "cancelacion", "voluntario": vid})

            for decision in decidir(self.estado(minuto)) or []:
                self.aplicar(minuto, decision)

        return self.resultado()

    def resultado(self):
        rescatadas = sum(r["comidas"] for r in self.recogidas.values() if r["rescatada"])
        total = sum(r["comidas"] for r in self.recogidas.values())
        minutos = sum(v["minutos_usados"] for v in self.voluntarios.values())
        horas = minutos / 60

        # En este orden, que es el de la clasificación: manda el primero y el
        # segundo solo desempata. Los dos redondeados a un decimal porque más
        # precisión sería fingir que la simulación la tiene.
        return {
            "metrica_principal": "porcentaje_salvado",
            "desempate": "comidas_por_hora",
            "porcentaje_salvado": round(100 * rescatadas / total, 1) if total else 0.0,
            "comidas_por_hora": round(rescatadas / horas, 1) if horas > 0 else 0.0,
            "comidas_rescatadas": rescatadas,
            "comidas_totales": total,
            "horas_voluntario": round(horas, 2),
            "recogidas_perdidas": sum(1 for r in self.recogidas.values() if not r["rescatada"]),
            "recogidas_totales": len(self.recogidas),
        }


# ── carga del asignador ─────────────────────────────────────────────────
def cargar(ruta):
    """Un módulo Python con `decidir(estado)`."""
    spec = importlib.util.spec_from_file_location("asignador", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.decidir


def por_proceso(comando):
    """Un ejecutable: recibe el estado por stdin, devuelve decisiones por stdout."""
    def decidir(estado):
        salida = subprocess.run(
            comando, shell=True, input=json.dumps(estado),
            capture_output=True, text=True, timeout=30,
        )
        if salida.returncode != 0:
            print(f"[aviso] el asignador ha fallado: {salida.stderr[:200]}", file=sys.stderr)
            return []
        return json.loads(salida.stdout or "[]")
    return decidir


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Simula un escenario contra tu asignador.")
    p.add_argument("--scenario", default="scenarios/sample_01.json")
    p.add_argument("--solver", help="ruta a un .py con decidir(estado)")
    p.add_argument("--cmd", help="ejecutable que lee stdin y escribe stdout")
    p.add_argument("--registro", help="dónde volcar el registro completo")
    a = p.parse_args()

    with open(a.scenario, encoding="utf-8") as f:
        escenario = json.load(f)

    if a.solver:
        decidir = cargar(a.solver)
    elif a.cmd:
        decidir = por_proceso(a.cmd)
    else:
        p.error("hace falta --solver o --cmd")

    sim = Simulador(escenario)
    resultado = sim.correr(decidir)

    if a.registro:
        with open(a.registro, "w", encoding="utf-8") as f:
            json.dump(sim.registro, f, ensure_ascii=False, indent=2)

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
