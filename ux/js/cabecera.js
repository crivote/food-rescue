/* ============================================================
   cabecera.js — barra de estado + cabecera con menu
   Marcado tomado del mockup v5; los datos salen del turno real.
   ============================================================ */

import { hhmm } from "./tiempo.js";
import { puntos, nivel } from "./estado.js";

/** Icono SVG por referencia al sprite de simbolos (en index.html). */
function ico(id) {
  return `<svg><use href="#${id}"/></svg>`;
}

export function barraEstado(min) {
  return `
  <div class="statusbar">
    <span>${hhmm(min)}</span>
    <span class="sb-r">
      ${ico("i-sig")}${ico("i-wifi")}
      <span class="bat">85</span>
    </span>
  </div>`;
}

export function cabecera(est) {
  const p = puntos(est);
  const nv = etiquetaNivel(est);
  const inicial = (est.voluntario.alias || "V").trim().charAt(0).toUpperCase();
  /* Si hay retrato se muestra; si no, la inicial. La inicial NO es un
     apaño: es la degradacion correcta si la foto no carga. */
  const retrato = est.voluntario.foto
    ? `<img src="${est.voluntario.foto}" alt="" width="224" height="224">`
    : inicial;
  return `
  <header class="head">
    <span><img src="assets/logo_trans.png" width="70" alt="NextFood"></span>
    <span class="spacer"></span>
    <span class="ava">${retrato}</span>
    <div class="kebab">
      <button aria-haspopup="true" aria-expanded="false" aria-label="Más opciones">${ico("i-dots")}</button>
      <div class="menu" role="menu">
        <div class="menu-head">
          <div class="nm">${est.voluntario.alias}</div>
          <div class="rw">Nivel: <b>${nv}</b> <svg class="shield"><use href="#i-shield"/></svg></div>
          <div class="pts">Puntos actuales: <b>${p.toLocaleString("es-ES")}</b></div>
        </div>
        <hr>
        <a role="menuitem" href="#">${ico("i-user")}Mi perfil</a>
        <a role="menuitem" href="#" class="danger">${ico("i-x")}Cancelar misión</a>
        <a role="menuitem" href="#" class="danger">${ico("i-power")}Terminar mi turno</a>
        <hr>
        <a role="menuitem" href="#">${ico("i-help")}FAQ</a>
        <a role="menuitem" href="#">${ico("i-chat")}Contactar equipo</a>
      </div>
    </div>
  </header>`;
}

/* puntos/nivel se derivan del estado, asi que la cabecera no puede
   desincronizarse del panel del turno. */
function etiquetaNivel(est) {
  return nivel(est).etiqueta.split("·").pop().trim();
}
