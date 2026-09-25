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
