/* ============================================================
   app.js — arranque y flujo del turno
   ------------------------------------------------------------
   Carga los datos, monta la pantalla y lleva las pulsaciones.
   Dos modos de vista:
     - app    (por defecto): una pantalla navegable, el recorrido real
     - lamina  (?modo=lamina): las 6 pantallas en fila, para diseno
   Ambas componen el MISMO marcado (pantallas.js).
   ============================================================ */

import { cargarTurno } from "./data.js";
import { nuevoEstado, FASE, siguienteMision, confirmarEntrega,
         cerrarTurno, haySiguienteMision, minutoTurno } from "./estado.js";
import { pantallaActual } from "./pantallas.js";
import { barraEstado, cabecera } from "./cabecera.js";
import { panelHTML, initPanel, initMenu } from "./panel.js";

/* ---------- montaje de una pantalla dentro de un .phone ---------- */

function montar(phone, est, extra = {}) {
  const screen = phone.querySelector(".screen");
  screen.innerHTML = pantallaActual(est, extra);

  /* cabecera y panel se rehacen con cada paso para que los puntos y
     la barra temporal sigan al estado sin poder desincronizarse */
  phone.querySelector(".statusbar")?.remove();
  phone.querySelector(".head")?.remove();
  phone.querySelector(".sheet")?.remove();

  /* La barra de estado del movil usa la MISMA hora que el panel del
     turno: si mostrara la hora real del sistema, en la maqueta
     convivirian dos relojes distintos y se leeria como un descuido. */
  phone.insertAdjacentHTML("afterbegin", cabecera(est) + barraEstado(minutoTurno(est)));
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
      /* Al cerrar la entrega no se puede aceptar mas de lo que se cargo. */
      const enCierre = est.fase === FASE.CIERRE;
      const base = enCierre ? (est.aceptadas ?? est.cargadas) : est.cargadas;
      const max = enCierre ? (est.cargadas ?? est.mision.raciones) : est.mision.raciones;
      const v = Math.max(0, Math.min(max, (base ?? max) + delta));
      if (enCierre) est.aceptadas = v; else est.cargadas = v;
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
      /* Cargado no es entregado: queda el viaje de vuelta y el cierre
         en el centro, donde puede rechazarse algo. Todavia sin puntos. */
      est.cargadas = est.cargadas ?? est.mision.raciones;
      est.fase = FASE.ENTREGA;
      pintar();
    } else if (/^Confirmar entrega/.test(txt)) {
      est.fase = FASE.CIERRE;
      pintar();
    } else if (/^Confirmo la entrega/.test(txt)) {
      /* La pantalla de exito deriva del estado las raciones entregadas y
         la subida de nivel; no se le pasan por parametro. */
      confirmarEntrega(est);
      pintar();
    } else if (/^Siguiente misi/.test(txt) || /^Terminar mi turno/.test(txt)) {
      if (haySiguienteMision(est)) {
        siguienteMision(est);
      } else {
        /* No se toca el boton a mano: el repintado lo sustituye y el
           cambio se perderia. El cierre vive en el estado. */
        cerrarTurno(est);
      }
      pintar({});
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
    { fase: FASE.ENTREGA,  extra: {} },
    { fase: FASE.CIERRE,   extra: {} },
    { fase: FASE.EXITO,    extra: {} },
  ];

  for (const f of fases) {
    const est = { ...base, fase: f.fase, cargadas: null };
    /* En la lamina la ultima pantalla muestra una entrega ya hecha. */
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
