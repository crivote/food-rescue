/* ============================================================
   mapa.js — el plano del trayecto
   ------------------------------------------------------------
   El fondo es una imagen de plano ILUSTRATIVA (assets/plano.webp).
   Las chinchetas NO van dentro de la imagen: van encima, en HTML,
   con posiciones en % (nombres.js -> posDe). Asi reubicar un punto
   es cambiar un numero, no regenerar el plano.

   El plano no es una proyeccion del escenario real: es un fondo
   creible. Lo que si es real es todo lo que dicen los rotulos.
   ============================================================ */

import { nombreDe, posDe, esCentro } from "./nombres.js";

/** Posicion en % del marcador de un punto. */
function pin(id, { yo = false, destino = false } = {}) {
  const { x, y } = posDe(id);
  const clase = yo ? "you" : (destino ? "mk" : "dot");
  /* El rotulo se ancla al lado con sitio: si el punto esta en la mitad
     derecha, el texto va hacia la izquierda y no se sale del recuadro. */
  const anclaje = x > 50 ? "lbl--izq" : "lbl--der";
  const etiqueta = yo ? ""
    : `<span class="lbl ${anclaje}" style="left:${x}%;top:${y}%">${nombreDe(id)}</span>`;
  return `<span class="${clase}" style="left:${x}%;top:${y}%"></span>${etiqueta}`;
}

/**
 * Plano para una mision: marcador propio, destino y los puntos de
 * referencia del turno (los que el voluntario ya conoce).
 *
 * @param {object} mision  mision actual del turno
 * @param {object} opts    { desde: id del punto de partida }
 */
export function planoHTML(mision, { desde = null } = {}) {
  const puntos = new Set([mision.recogida, mision.centro]);
  if (desde) puntos.add(desde);

  const marcas = [...puntos].map((id) => pin(id, {
    destino: id === mision.recogida || id === mision.centro,
  })).join("");

  return `
    <div class="map">
      <span class="chip"><svg><use href="#i-clock"/></svg>caduca a las ${hhmmCaduca(mision)}</span>
      <img class="plano" src="assets/plano.webp" alt="Plano del trayecto">
      ${trazadoHTML(mision, desde)}
      ${marcas}
      ${pin(desde ?? mision.recogida, { yo: true })}
    </div>`;
}

/** Linea punteada entre el punto de partida y el destino. */
function trazadoHTML(mision, desde) {
  const a = posDe(desde ?? mision.recogida);
  const b = posDe(mision.recogida === (desde ?? mision.recogida) ? mision.centro : mision.recogida);
  return `<svg class="trazado" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
    <path d="M ${a.x} ${a.y} L ${b.x} ${b.y}" fill="none" stroke="#1F7A4D"
      stroke-width="0.7" stroke-dasharray="2.2 2.2" vector-effect="non-scaling-stroke"/>
  </svg>`;
}

function hhmmCaduca(m) {
  const t = ((Math.round(m.caduca_min) % 1440) + 1440) % 1440;
  return String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(t % 60).padStart(2, "0");
}

/**
 * Barra de progreso del trayecto (recorrido/ETA).
 * Por defecto el tramo de ida; el de vuelta al centro pasa sus cifras.
 */
export function trayectoHTML(m, { km = m.km_ida, min = m.min_ida } = {}) {
  return `
    <div class="trip">
      <div class="bar"><i style="width:40%"></i><span class="knob" style="left:40%"></span></div>
      <div class="lab"><span>recorrido ${km} km</span><span><b>unos ${min} min</b></span></div>
    </div>`;
}
