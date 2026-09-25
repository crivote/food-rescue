/* ============================================================
   panel.js — panel inferior del turno (deslizable)
   ------------------------------------------------------------
   La barra temporal y "te quedan X" siempre visibles; raciones y
   km solo al desplegar. El alto del panel se publica en la
   variable CSS --sheet-h para que el area desplazable reserve
   sitio y NO tape los botones (defecto del mockup).
   ============================================================ */

import { hhmm, duracion, fraccion } from "./tiempo.js";
import { puntos, entregadas, nivel } from "./estado.js";

function ico(id) {
  return `<svg><use href="#${id}"/></svg>`;
}

export function panelHTML(est) {
  const [ini, fin] = est.voluntario.turno;
  const min = est.mision.t;
  const pct = Math.round(fraccion(min, ini, fin) * 100);
  return `<div class="sheet">
    <div class="grip-zone" role="button" tabindex="0" aria-expanded="false" aria-label="Mostrar u ocultar panel del turno">
      <div class="grip"></div>
      <div class="srow"><span class="sttl">Tu ayuda hoy</span><span class="srem">te quedan ${duracion(fin - min)}</span></div>
      <div class="tl">
        <div class="bar"><i style="width:${pct}%"></i><span class="now" style="left:${pct}%"></span></div>
        <div class="lab"><span>${hhmm(ini)}</span><span>ahora <b>${hhmm(min)}</b></span><span>${hhmm(fin)}</span></div>
      </div>
    </div>
    <div class="sheet-detail">
      <div class="stats">
        <div class="stat"><span class="ic">${ico("i-basket")}</span>
          <span><span class="v">${entregadas(est)}</span><br><span class="k"> raciones salvadas</span></span></div>
        <div class="stat"><span class="ic">${ico("i-clock")}</span>
          <span><span class="v">${duracion(fin - min)}</span><br><span class="k">de turno restante</span></span></div>
      </div>
    </div>
  </div>`;
}

export function initPanel(phone) {
  const sh = phone.querySelector(".sheet");
  const zone = phone.querySelector(".grip-zone");
  if (!sh || !zone) return;

  let maxT = 0, startT = 0, curT = 0, startY = 0, moved = 0, dragging = false, pid = null;

  const measure = () => {
    maxT = Math.max(0, sh.offsetHeight - zone.offsetHeight);
    /* Alto REAL que tapa el panel colapsado: la zona visible (la que se
       arrastra) mas el padding inferior del propio panel, mas un margen
       de respiro. Se publica como --sheet-h para que el area desplazable
       reserve ese hueco y no tape los botones. */
    const PADDING_PANEL = 18, MARGEN = 10;
    const h = zone.offsetHeight + PADDING_PANEL + MARGEN;
    phone.style.setProperty("--sheet-h", h + "px");
  };
  const apply = (t) => {
    curT = t;
    sh.style.transform = `translateY(${t}px)`;
    zone.setAttribute("aria-expanded", String(t === 0));
  };

  measure(); apply(maxT);
  requestAnimationFrame(() => { measure(); apply(maxT); });
  window.addEventListener("load", () => { measure(); apply(maxT); });
  window.addEventListener("resize", () => { measure(); apply(Math.min(curT, maxT)); });

  zone.addEventListener("pointerdown", (e) => {
    dragging = true; moved = 0; startT = curT; startY = e.clientY; pid = e.pointerId;
    try { zone.setPointerCapture(pid); } catch (_) {}
    sh.classList.add("dragging");
  });
  zone.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const dy = e.clientY - startY;
    moved = Math.max(moved, Math.abs(dy));
    apply(Math.max(0, Math.min(maxT, startT + dy)));
  });
  function end() {
    if (!dragging) return;
    dragging = false;
    sh.classList.remove("dragging");
    try { zone.releasePointerCapture(pid); } catch (_) {}
    if (moved < 5) apply(curT < maxT / 2 ? maxT : 0);
    else apply(curT < maxT / 2 ? 0 : maxT);
  }
  zone.addEventListener("pointerup", end);
  zone.addEventListener("pointercancel", end);
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      apply(curT === 0 ? maxT : 0);
    }
  });
}

/** Conecta el boton de opciones (kebab) de la cabecera. */
export function initMenu(root) {
  root.addEventListener("click", (e) => {
    const kb = e.target.closest(".kebab");
    root.querySelectorAll(".kebab.open").forEach((k) => {
      if (k !== kb) {
        k.classList.remove("open");
        k.querySelector("button")?.setAttribute("aria-expanded", "false");
      }
    });
    if (kb) {
      const o = kb.classList.toggle("open");
      kb.querySelector("button")?.setAttribute("aria-expanded", String(o));
    }
  });
  root.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    root.querySelectorAll(".kebab.open").forEach((k) => {
      k.classList.remove("open");
      k.querySelector("button")?.setAttribute("aria-expanded", "false");
    });
  });
}
