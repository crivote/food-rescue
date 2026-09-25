/* ============================================================
   tiempo.js — relojes del turno
   ------------------------------------------------------------
   El escenario cuenta en minutos desde la medianoche (1170 = 19:30).
   El voluntario lee horas de reloj. Aqui vive esa traduccion.
   ============================================================ */

/** 1170 -> "19:30" */
export function hhmm(min) {
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
}

/** Minutos que faltan de `ahora` a `fin`, nunca negativo. */
export function restante(ahora, fin) {
  return Math.max(0, fin - ahora);
}

/** "2 h 10 min" / "45 min" */
export function duracion(min) {
  const m = Math.max(0, Math.round(min));
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

/** Posicion 0..1 de `ahora` dentro de [ini, fin]. */
export function fraccion(ahora, ini, fin) {
  if (fin <= ini) return 0;
  return Math.max(0, Math.min(1, (ahora - ini) / (fin - ini)));
}

/* ------------------------------------------------------------
   El reloj DENTRO de una mision
   ------------------------------------------------------------
   `m.t` es la hora REAL a la que el plan saca al voluntario hacia
   esa mision, y es un valor fijo: dentro de la mision no cambia.
   Si el reloj se quedara clavado ahi, el turno restante y la barra
   temporal solo se moverian al cerrar cada entrega. Con los minutos
   de cada tramo (que ya vienen en los datos) el reloj avanza paso a
   paso: 0 al aceptar la mision, el tramo de ida al llegar al
   comercio, el de vuelta al llegar al centro. Medido sobre la traza
   real de v05, el turno cierra a las 21:27 y dura 108 min de camino,
   asi que la progresion cuadra con el plan sin salirse de la ventana.
   ------------------------------------------------------------ */

/** Etapa del reloj dentro de una mision. */
export const ETAPA = {
  ASIGNADA: 0,   // aun no ha salido
  CAMINO: 1,     // acaba de salir hacia el comercio
  RECOGIDA: 2,   // ya en el comercio
  ENTREGA: 3,    // acaba de salir hacia el centro
  CIERRE: 4,     // ya en el centro
};

/**
 * Minutos de RECORRIDO de esta mision ya completados en `etapa`.
 *
 * Ojo: se cuenta el recorrido, no el rato de cargar ni el de descargar.
 * Esos tiempos no estan en los datos del plan, y si se inventaran al
 * alza el reloj de la mision siguiente arrancaria antes de que esta
 * cerrase (la traza real deja solo 1 min de holgura entre la mision 3 y
 * la 4). Con los tramos reales, la secuencia es monotona y el turno
 * cierra dentro de su ventana.
 */
export function recorridoHasta(etapa, m) {
  switch (etapa) {
    case ETAPA.RECOGIDA:
    case ETAPA.ENTREGA: return m.min_ida;
    case ETAPA.CIERRE:  return m.min_ida + m.min_vuelta;
    default:            return 0;
  }
}

/**
 * Minuto del reloj para la etapa actual de una mision.
 *
 * `m.t` es la hora REAL a la que el plan saca al voluntario hacia esa
 * mision, y es fijo dentro de ella: el reloj de la mision es esa hora
 * mas el recorrido ya hecho. NO se acumulan los tramos de las misiones
 * anteriores porque ya estan dentro de cada `t`.
 */
export function avanceReloj(m, etapa) {
  return m.t + recorridoHasta(etapa, m);
}
