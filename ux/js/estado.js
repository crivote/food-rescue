/* ============================================================
   estado.js — estado del turno en memoria
   ------------------------------------------------------------
   Guarda en que mision va el voluntario y cuanto lleva salvado.
   Los puntos y el nivel NO se acumulan a mano: se derivan de las
   raciones entregadas, para que no puedan desincronizarse.
   ============================================================ */

import { puntosPor, nivelDe, subeDeNivel, progresoNivel } from "./gamificacion.js";

/** Fases de una mision, en orden. */
export const FASE = {
  ASIGNADA: "asignada",
  CAMINO: "camino",
  RECOGIDA: "recogida",
  ENTREGA: "entrega",
  EXITO: "exito",
};

export function nuevoEstado(turno) {
  return {
    turno,
    voluntario: turno.voluntario,
    indice: 0,                       // mision actual (0-based)
    fase: FASE.ASIGNADA,
    racionesTurno: 0,                // entregadas en lo que va de turno
    puntosBase: turno.puntos_base,
    cargadas: null,                  // raciones confirmadas en esta mision
    mision: turno.misiones[0],
  };
}

/** Raciones entregadas hasta ahora (incluye la mision en curso si ya se entrego). */
export function entregadas(est) {
  return est.racionesTurno;
}

/** Puntos totales = base + 10 por racion entregada. Siempre derivados. */
export function puntos(est) {
  return est.puntosBase + puntosPor(entregadas(est));
}

export function nivel(est) {
  return nivelDe(puntos(est));
}

export function progreso(est) {
  return progresoNivel(puntos(est));
}

/** ¿La ultima entrega ha hecho subir de nivel? */
export function haSubidoDeNivel(est) {
  return subeDeNivel(est.puntosBase + puntosPor(entregadas(est) - entregadasMisionActual(est)),
                     puntos(est));
}

function entregadasMisionActual(est) {
  return est.cargadas ?? 0;
}

export function haySiguienteMision(est) {
  return est.indice < est.turno.misiones.length - 1;
}

/** Avanza a la mision siguiente. Devuelve false si era la ultima. */
export function siguienteMision(est) {
  if (!haySiguienteMision(est)) return false;
  est.indice += 1;
  est.mision = est.turno.misiones[est.indice];
  est.fase = FASE.ASIGNADA;
  est.cargadas = null;
  return true;
}

/**
 * Confirma la entrega de la mision en curso: suma las raciones y
 * pasa a la pantalla de exito.
 */
export function confirmarEntrega(est) {
  const n = est.cargadas ?? est.mision.raciones;
  est.racionesTurno = est.racionesTurno + n;
  est.fase = FASE.EXITO;
  return n;
}

/** Minuto del reloj correspondiente a la mision actual. */
export function ahora(est) {
  return est.mision.t;
}

/** Resumen del turno para la pantalla final. */
export function resumenTurno(est) {
  return {
    raciones: entregadas(est),
    puntos: puntos(est),
    nivel: nivel(est),
    misiones: est.turno.misiones.length,
    objetivo: est.turno.objetivo_turno,
    objetivoCumplido: entregadas(est) >= est.turno.objetivo_turno,
  };
}
