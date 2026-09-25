/* ============================================================
   nombres.js — el diccionario id -> nombre legible
   ------------------------------------------------------------
   Los identificadores del escenario (r32, c5, v05...) son
   andamiaje interno: existen en los datos y en el codigo, pero
   NUNCA deben llegar a la pantalla. Este modulo es la frontera:
   todo lo que se muestra al voluntario pasa por nombreDe().

   Si un id no esta en el diccionario, el fallback devuelve una
   descripcion generica LEGIBLE, jamas el id crudo.
   ============================================================ */

/* Comercios que recogen comida. Nombres, direcciones y fotos ficticios.
   La foto se llama por el nombre del local, NUNCA por su id: asi el
   repositorio publico no revela la nomenclatura del escenario. */
const COMERCIOS = {
  r32: { nombre: "Supermercado El Huerto",   direccion: "Calle del Almendro 12",
         foto: "supermercado-huerto" },
  r15: { nombre: "Panadería La Espiga",      direccion: "Calle del Molino 8",
         foto: "panaderia-espiga" },
  r27: { nombre: "Frutería El Vergel",       direccion: "Avenida de los Olivos 45",
         foto: "fruteria-vergel" },
  r24: { nombre: "Restaurante La Mesa",      direccion: "Calle de la Fuente 3" },
  r25: { nombre: "Mercado de la Ribera",     direccion: "Paseo del Río 30" },
  r09: { nombre: "Panificadora Central",     direccion: "Calle Norte 17" },
};

/* Centros donde se entrega la comida. Nombres ficticios. */
const CENTROS = {
  c5: { nombre: "Comedor La Concordia",  direccion: "Calle de la Concordia 21" },
  /* c3 es un CENTRO de entrega del escenario (destino con capacidad de
     almacenaje), no un comercio: el nombre tiene que sonar a destino grande. */
  c3: { nombre: "Banco de Alimentos · Nave Norte", direccion: "Polígono Arboleda, nave 7" },
};

const NOMBRES = { ...COMERCIOS, ...CENTROS };

/* Un punto de recogida y su centro de entrega son cosas distintas
   y el voluntario necesita distinguirlas de un vistazo. */
export function esCentro(id) {
  return Object.prototype.hasOwnProperty.call(CENTROS, id);
}

/**
 * Nombre legible de un punto. Nunca devuelve el id crudo.
 */
export function nombreDe(id) {
  const e = NOMBRES[id];
  if (e) return e.nombre;
  return esCentro(id) ? "Centro de entrega" : "Punto de recogida";
}

/**
 * Direccion legible. Vacia si no la conocemos (mejor nada que un id).
 */
export function direccionDe(id) {
  const e = NOMBRES[id];
  return e ? e.direccion : "";
}

/**
 * Ruta de la foto del local, o cadena vacia si aun no hay ninguna.
 * Devolver vacio es importante: quien la use decide que hacer sin foto
 * en vez de recibir una imagen rota.
 */
export function fotoDe(id) {
  const e = NOMBRES[id];
  return e && e.foto ? `assets/${e.foto}.webp` : "";
}

/** "Nombre, Direccion" o solo el nombre si no hay direccion. */
export function lugarCompleto(id) {
  const d = direccionDe(id);
  return d ? `${nombreDe(id)}, ${d}` : nombreDe(id);
}

/**
 * Para el plano: posicion de cada punto en % sobre el contenedor.
 * Es una colocacion ILUSTRATIVA, no una proyeccion del escenario:
 * el plano es un fondo creible, no un mapa a escala.
 * La ruta del turno sube de sur a norte, asi que se ordena en vertical.
 */
export const PLANO_POS = {
  r32: { x: 20, y: 88 },
  c5:  { x: 72, y: 72 },
  r15: { x: 24, y: 56 },
  r27: { x: 34, y: 40 },
  r24: { x: 56, y: 24 },
  c3:  { x: 28, y: 10 },
};

/** Posicion en % de un punto; si falta, se centra (nunca un id). */
export function posDe(id) {
  return PLANO_POS[id] || { x: 50, y: 50 };
}
