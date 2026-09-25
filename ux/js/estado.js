/* ============================================================
   estado.js — estado del turno en memoria
   ------------------------------------------------------------
   Guarda en que mision va el voluntario y cuanto lleva salvado.
   Los puntos y el nivel NO se acumulan a mano: se derivan de las
   raciones entregadas, para que no puedan desincronizarse.
   ============================================================ */

import { puntosPor, nivelDe, subeDeNivel, progresoNivel } from "./gamificacion.js";
import { ETAPA, avanceReloj } from "./tiempo.js";

/** Fases de una mision, en orden. */
export const FASE = {
  ASIGNADA: "asignada",
  CAMINO: "camino",        // de camino al comercio
  RECOGIDA: "recogida",    // confirmar lo que se carga
  ENTREGA: "entrega",      // de camino al centro de entrega
  CIERRE: "cierre",        // confirmar lo que se queda alli
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
    cargadas: null,                  // raciones confirmadas al recoger
    aceptadas: null,                 // raciones que se quedan en el centro
    cerrado: false,                  // el turno ya se ha terminado
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

/**
 * Raciones de la mision en curso. MISMA cadena de respaldo que
 * `confirmarEntrega`, para que el "antes" y el "despues" que compara
 * `haSubidoDeNivel` se refieran a la misma cantidad.
 */
function entregadasMisionActual(est) {
  return est.aceptadas ?? est.cargadas ?? est.mision.raciones;
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
  est.aceptadas = null;
  return true;
}

/**
 * Cierra el turno: la ultima entrega ya se confirmo y no queda ninguna
 * mision. Marca el estado en vez de tocar el boton a mano, porque el
 * siguiente repintado rehace el marcado y cualquier cambio hecho sobre
 * el nodo viejo se pierde (el clic parecia no hacer nada).
 */
export function cerrarTurno(est) {
  est.cerrado = true;
  est.fase = FASE.EXITO;
}

/**
 * Confirma la entrega de la mision en curso: suma las raciones y
 * pasa a la pantalla de exito.
 *
 * Cuenta lo ACEPTADO, no lo cargado: por el camino algo puede
 * estropearse o el centro puede rechazar lo que no esta en condiciones.
 */
export function confirmarEntrega(est) {
  const n = est.aceptadas ?? est.cargadas ?? est.mision.raciones;
  est.racionesTurno = est.racionesTurno + n;
  est.fase = FASE.EXITO;
  return n;
}

/**
 * Etapa del reloj segun la fase del flujo. Al aceptar la mision aun no
 * se ha salido, asi que el reloj se queda en la hora de asignacion; a
 * partir de ahi avanza con los tramos.
 */
export function etapaDe(est) {
  switch (est.fase) {
    case FASE.CAMINO:   return ETAPA.CAMINO;
    case FASE.RECOGIDA: return ETAPA.RECOGIDA;
    case FASE.ENTREGA:  return ETAPA.ENTREGA;
    case FASE.CIERRE:
    case FASE.EXITO:    return ETAPA.CIERRE;
    default:            return ETAPA.ASIGNADA;
  }
}

/**
 * Minuto del reloj correspondiente al momento actual del turno. NO es
 * la hora de asignacion de la mision: es esa hora mas lo que el
 * voluntario lleva andado DENTRO de la mision en curso.
 */
export function minutoTurno(est) {
  return avanceReloj(est.mision, etapaDe(est));
}

/** Minutos de camino de las misiones ya cerradas. */
export function caminoAcumulado(est) {
  return est.turno.misiones
    .slice(0, est.indice)
    .reduce((s, m) => s + m.min_ida + m.min_vuelta, 0);
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
