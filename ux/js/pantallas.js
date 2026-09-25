/* ============================================================
   pantallas.js — las pantallas del flujo
   ------------------------------------------------------------
   UNICA FUENTE del marcado: tanto el modo app (navegable) como el
   modo lamina (vista de diseno) componen estas mismas funciones.
   Duplicar el marcado es la forma segura de que los dos modos se
   desincronicen al primer cambio.

   Principio rector: nada de vocabulario tecnico, ningun id del
   escenario, y cada frase tiene que sostenerse ante alguien que no
   sabe nada del sistema.
   ============================================================ */

import { nombreDe, direccionDe, fotoDe } from "./nombres.js";
import { hhmm } from "./tiempo.js";
import { planoHTML, trayectoHTML } from "./mapa.js";
import { puntosPor } from "./gamificacion.js";
import { FASE, haySiguienteMision, resumenTurno, nivel } from "./estado.js";

function ico(id) {
  return `<svg><use href="#${id}"/></svg>`;
}

/* ---------- piezas reutilizables ---------- */

/** Fila de un punto del itinerario (recogida o entrega). */
function legItem(icono, etiqueta, id) {
  const dir = direccionDe(id);
  return `
    <div class="leg-item">
      <span class="ic">${ico(icono)}</span>
      <span><span class="lb">${etiqueta}</span>
        <p class="vl">${nombreDe(id)}${dir ? " <br> " + dir : ""}</p>
      </span>
    </div>`;
}

/**
 * Foto del local para reconocerlo al llegar. Si el local aun no tiene
 * foto propia, no se pinta nada: mejor hueco ausente que imagen rota.
 */
function fotoLocal(id) {
  const src = fotoDe(id);
  if (!src) return "";
  return `
    <figure class="foto">
      <img src="${src}" alt="${nombreDe(id)}" width="640" height="640" loading="lazy" decoding="async">
      <figcaption class="foto__cap">Así reconocerás el local</figcaption>
    </figure>`;
}

/** Stepper de 4 pasos de la mision. `activo` = 1..4. */
function stepper(activo) {
  const pasos = ["Ir al punto de recogida", "Confirmar carga", "Ir al punto de recepción", "Confirmar entrega"];
  const items = pasos.map((txt, i) => {
    const n = i + 1;
    let dot, lab;
    if (n < activo) {
      dot = `<div class="mission-stepper__dot mission-stepper__dot--done">
               <svg viewBox="0 0 24 24"><polyline points="4 12 10 18 20 6" /></svg></div>`;
      lab = `<span class="mission-stepper__label mission-stepper__label--done">${txt}</span>`;
    } else if (n === activo) {
      dot = `<div class="mission-stepper__dot mission-stepper__dot--active">${n}</div>`;
      lab = `<span class="mission-stepper__label mission-stepper__label--active">${txt}</span>`;
    } else {
      dot = `<div class="mission-stepper__dot mission-stepper__dot--pending">${n}</div>`;
      lab = `<span class="mission-stepper__label">${txt}</span>`;
    }
    return `<div class="mission-stepper__step">${dot}${lab}</div>`;
  }).join("");

  return `
    <div class="mission-stepper">
      <p class="mission-stepper__title">Misión asignada</p>
      <div class="mission-stepper__track mission-stepper__track--p${activo - 1}">${items}</div>
    </div>`;
}

function acts(primario, secundario) {
  return `<div class="acts">
    <button class="btn solid">${ico(primario.icono)}${primario.texto}</button>
    ${secundario ? `<button class="cancel-link">${secundario}</button>` : ""}
  </div>`;
}

/* ---------- 1 · MISIÓN ASIGNADA ---------- */

export function pantallaMision(est) {
  const m = est.mision;
  const n = Math.min(est.indice + 1, est.turno.misiones.length);
  const total = est.turno.misiones.length;
  const cabe = m.raciones >= 25;
  const motivo = cabe
    ? "Por tu capacidad de transporte eres de las pocas personas que pueden recogerlo antes de que caduque."
    : "Está cerca de ti y caduca pronto: puedes llegar con tiempo de sobra.";

  return `
    <div class="pitch">
      <span class="heart">${ico("i-heart")}</span>
      <h2>Marca la diferencia</h2>
      <p>${motivo}</p>
    </div>

    <div class="card">
      <span class="eyebrow">Misión ${n} de ${total}</span>
      <div class="leg">
        ${legItem("i-store", "Recogida", m.recogida)}
        ${legItem("i-pin", "Entrega", m.centro)}
      </div>
      <div class="pills">
        <span class="pill">${ico("i-box")}${m.raciones} raciones</span>
        <span class="pill amber">${ico("i-clock")}caduca ${hhmm(m.caduca_min)}</span>
        <span class="pill">${ico("i-truck")}unos ${m.min_ida + m.min_vuelta} min</span>
        <span class="pill">${ico("i-star")}+${puntosPor(m.raciones)} pts</span>
      </div>
    </div>

    ${acts({ icono: "i-check", texto: "Aceptar misión" }, "No puedo hacer esta misión")}`;
}

/* ---------- 2 · EN CAMINO ---------- */

export function pantallaCamino(est, desde) {
  const m = est.mision;
  return `
    ${stepper(1)}
    <div class="card">
      <span class="eyebrow">En camino</span>
      <h2>Al punto de recogida</h2>
      <p class="sub" style="display:flex;align-items:center;gap:5px">
        <svg style="width:18px;height:18px;stroke:var(--solid);fill:none;stroke-width:1.8"><use href="#i-pin"/></svg>
        ${nombreDe(m.recogida)}<br>${direccionDe(m.recogida)}
      </p>
      ${planoHTML(m, { desde })}
      ${trayectoHTML(m)}
    </div>
    ${acts({ icono: "i-pin", texto: "Confirmar llegada" }, "Cancelo la recogida")}`;
}

/* ---------- 3 · RECOGIDA ---------- */

export function pantallaRecogida(est) {
  const m = est.mision;
  const cargadas = est.cargadas ?? m.raciones;
  return `
    ${stepper(2)}
    <div class="card">
      <span class="eyebrow">Has llegado</span>
      <h2>Recoge la comida</h2>
      <p class="sub" style="display:flex;align-items:center;gap:5px">
        <svg style="width:18px;height:18px;stroke:var(--solid);fill:none;stroke-width:1.8"><use href="#i-pin"/></svg>
        ${nombreDe(m.recogida)}<br>${direccionDe(m.recogida)}
      </p>
      ${fotoLocal(m.recogida)}
      <p>Confirma cuántas raciones cargas realmente:</p>
      <div class="card load">
        <span class="eyebrow">Carga confirmada</span>
        <div class="stepper" data-value="${cargadas}">
          <button class="st-minus" aria-label="Quitar ración">${ico("i-minus")}</button>
          <span class="val">${cargadas}</span>
          <button class="st-plus" aria-label="Añadir ración">${ico("i-plus")}</button>
        </div>
        <div class="cap">raciones en tu caja</div>
        <div class="hint">ajusta el número si el resultado difiere del previsto</div>
      </div>
    </div>
    ${acts({ icono: "i-truck", texto: "Confirmo la carga y la entrego" }, "Cancelo la recogida")}`;
}

/* ---------- 4 · ÉXITO ---------- */

export function pantallaExito(est, { racionesEntregadas, subeNivel }) {
  const m = est.mision;
  const r = resumenTurno(est);
  const nv = nivel(est);

  const logros = [];
  if (subeNivel) {
    logros.push(`<div class="ach">
        <span class="ic">${ico("i-up")}</span>
        <span><t>¡Has subido de nivel!</t><s>${nv.etiqueta}</s></span>
      </div>`);
  }
  if (r.objetivoCumplido) {
    logros.push(`<div class="ach">
        <span class="ic">${ico("i-medal")}</span>
        <span><t>Objetivo del turno cumplido</t><s>${r.objetivo} raciones salvadas hoy</s></span>
      </div>`);
  } else {
    const falta = Math.max(0, r.objetivo - r.raciones);
    logros.push(`<div class="ach">
        <span class="ic">${ico("i-star")}</span>
        <span><t>A un paso del objetivo</t><s>te faltan ${falta} raciones para la insignia del turno</s></span>
      </div>`);
  }

  const siguiente = haySiguienteMision(est)
    ? "Siguiente misión"
    : "Terminar mi turno por hoy";

  return `
    <div class="card succ" style="text-align:center">
      <div class="halo">${ico("i-check")}</div>
      <div class="num">${racionesEntregadas} raciones</div>
      <p class="sub" style="display:flex;align-items:center;justify-content:center;gap:5px">
        <svg style="width:13px;height:13px;stroke:var(--solid);fill:none;stroke-width:1.8"><use href="#i-clock"/></svg>
        salvadas antes de caducar · ${hhmm(m.caduca_min)}
      </p>
      <span class="pill amber" style="margin-top:9px;display:inline-flex">${ico("i-star")}+${puntosPor(racionesEntregadas)} pts</span>
      ${logros.join("")}
    </div>
    ${acts({ icono: "i-arrow", texto: siguiente }, null)}`;
}

/** Enrutador: la pantalla que toca segun la fase del estado. */
export function pantallaActual(est, extra = {}) {
  switch (est.fase) {
    case FASE.CAMINO:   return pantallaCamino(est, extra.desde);
    case FASE.RECOGIDA: return pantallaRecogida(est);
    case FASE.EXITO:    return pantallaExito(est, extra);
    default:            return pantallaMision(est);
  }
}
