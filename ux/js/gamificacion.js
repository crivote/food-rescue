/* ============================================================
   gamificacion.js — puntos, niveles y objetivos
   ------------------------------------------------------------
   Un punto por racion rescatada. Los nombres de nivel son
   deliberadamente neutros (no "Voluntario"/"Rescatador") para
   que la interfaz no presuponga el genero de quien la usa.
   ============================================================ */

export const PTS_POR_RACION = 10;

export const NIVELES = [
  [0,    "Nivel 1 · Primeros pasos"],
  [150,  "Nivel 2 · Colaboración"],
  [400,  "Nivel 3 · Voluntariado"],
  [900,  "Nivel 4 · Rescate"],
  [1500, "Nivel 5 · Líder de turno"],
];

/** Puntos que aporta rescatar n raciones. */
export function puntosPor(raciones) {
  return raciones * PTS_POR_RACION;
}

/** Nivel alcanzado con un total de puntos -> { indice, etiqueta, umbral }. */
export function nivelDe(puntos) {
  let idx = 0;
  for (let i = 0; i < NIVELES.length; i++) {
    if (puntos >= NIVELES[i][0]) idx = i;
  }
  return { indice: idx, etiqueta: NIVELES[idx][1], umbral: NIVELES[idx][0] };
}

/** true si al pasar de `antes` a `ahora` se ha subido de nivel. */
export function subeDeNivel(antes, ahora) {
  return nivelDe(ahora).indice > nivelDe(antes).indice;
}

/** Progreso 0..1 hacia el siguiente nivel (1 si ya esta en el ultimo). */
export function progresoNivel(puntos) {
  const { indice } = nivelDe(puntos);
  if (indice >= NIVELES.length - 1) return 1;
  const desde = NIVELES[indice][0];
  const hasta = NIVELES[indice + 1][0];
  return Math.max(0, Math.min(1, (puntos - desde) / (hasta - desde)));
}
