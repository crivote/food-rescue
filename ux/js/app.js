/* ============================================================
   app.js — arranque y flujo del turno
   ------------------------------------------------------------
   Carga los datos, monta la pantalla y lleva las pulsaciones.
   Dos modos de vista:
     - app    (por defecto): una pantalla navegable, el recorrido real
     - lamina  (?modo=lamina): las 4 pantallas en fila, para diseno
   Ambas componen el MISMO marcado (pantallas.js).
   ============================================================ */

import { cargarTurno } from "./data.js";
import { nuevoEstado, FASE, siguienteMision, confirmarEntrega,
         haySiguienteMision } from "./estado.js";
import { pantallaActual } from "./pantallas.js";
import { barraEstado, cabecera } from "./cabecera.js";
import { panelHTML, initPanel, initMenu } from "./panel.js";

/* ---------- montaje de una pantalla dentro de un .phone ---------- */

function montar(phone, est, extra = {}) {
  const min = est.mision.t;
  const screen = phone.querySelector(".screen");
  screen.innerHTML = pantallaActual(est, extra);

  /* cabecera y panel se rehacen con cada paso para que los puntos y
     la barra temporal sigan al estado sin poder desincronizarse */
  phone.querySelector(".statusbar")?.remove();
  phone.querySelector(".head")?.remove();
  phone.querySelector(".sheet")?.remove();

  phone.insertAdjacentHTML("afterbegin", cabecera(est) + barraEstado(min));
  phone.insertAdjacentHTML("beforeend", panelHTML(est));
  initPanel(phone);
}

/* ---------- estado de partida de una mision ---------- */

function desdeDe(est) {
  return est.indice > 0 ? est.turno.misiones[est.indice - 1].centro : null;
}

/* ---------- modo APP: recorrido navegable ---------- */

async function modoApp() {
  const turno = await cargarTurno();
  const est = nuevoEstado(turno);

  const phone = document.createElement("main");
  phone.className = "phone";
  phone.innerHTML = `<div class="screen"></div>`;
  document.body.appendChild(phone);

  let ultimoExtra = {};

  function pintar(extra = ultimoExtra) {
    ultimoExtra = extra;
    montar(phone, est, extra);
  }

  /* delegacion: un solo listener sobrevive a los re-render */
  phone.addEventListener("click", (e) => {
    const b = e.target.closest("button, .st-plus, .st-minus");
    if (!b) return;

    if (b.classList.contains("st-plus") || b.classList.contains("st-minus")) {
      const st = b.closest(".stepper");
      const delta = b.classList.contains("st-plus") ? 1 : -1;
      const max = est.mision.raciones;
      const v = Math.max(0, Math.min(max, (est.cargadas ?? max) + delta));
      est.cargadas = v;
      st.dataset.value = v;
      st.querySelector(".val").textContent = v;
      return;
    }

    const txt = b.textContent.trim();

    if (/^Aceptar misi/.test(txt)) {
      est.fase = FASE.CAMINO;
      pintar({ desde: desdeDe(est) });
    } else if (/^Confirmar llegada/.test(txt)) {
      est.fase = FASE.RECOGIDA;
      pintar();
    } else if (/^Confirmo la carga/.test(txt)) {
      const antes = est.puntosBase + (est.racionesTurno * 10);
      const n = confirmarEntrega(est);
      const despues = est.puntosBase + (est.racionesTurno * 10);
      pintar({ racionesEntregadas: n, subeNivel: Math.floor(despues / 900) > Math.floor(antes / 900) });
    } else if (/^Siguiente misi/.test(txt) || /^Terminar mi turno/.test(txt)) {
      if (haySiguienteMision(est)) {
        siguienteMision(est);
        pintar({});
      } else {
        pintar({});
        b.textContent = "Turno completado · ¡gracias!";
        b.disabled = true;
      }
    }
  });

  initMenu(document.body);
  pintar({});
}

/* ---------- modo LÁMINA: las 4 pantallas en fila ---------- */

async function modoLamina() {
  const turno = await cargarTurno();
  const base = nuevoEstado(turno);

  const fases = [
    { fase: FASE.ASIGNADA, extra: {} },
    { fase: FASE.CAMINO,   extra: { desde: null } },
    { fase: FASE.RECOGIDA, extra: {} },
    { fase: FASE.EXITO,    extra: { racionesEntregadas: base.mision.raciones, subeNivel: false } },
  ];

  for (const f of fases) {
    const est = { ...base, fase: f.fase, cargadas: null };
    if (f.fase === FASE.EXITO) est.racionesTurno = base.mision.raciones;
    const phone = document.createElement("section");
    phone.className = "phone";
    phone.innerHTML = `<div class="screen"></div>`;
    document.body.appendChild(phone);
    montar(phone, est, f.extra);
  }
  initMenu(document.body);
}

/* ---------- arranque ---------- */

function mostraError(e) {
  document.body.innerHTML =
    `<div style="max-width:640px;margin:60px auto;font:15px/1.6 system-ui;padding:0 20px">
      <h2 style="margin:0 0 10px">No se pudo cargar la demostración</h2>
      <p style="color:#B4533A">${e.message}</p>
      <p style="color:#6B7A70">Si has abierto el fichero con doble clic, sirve la carpeta
      por HTTP: <code>python3 -m http.server</code></p>
    </div>`;
  console.error(e);
}

const modo = new URLSearchParams(location.search).get("modo");
document.body.classList.add(modo === "lamina" ? "modo-lamina" : "modo-app");

(modo === "lamina" ? modoLamina() : modoApp()).catch(mostraError);
