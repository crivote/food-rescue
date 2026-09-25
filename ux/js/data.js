/* ============================================================
   data.js — carga de los datos del turno
   ------------------------------------------------------------
   Los datos se piden por fetch a data/turno.json. Eso implica que
   la pagina necesita servirse por HTTP: abrirla con doble clic
   (file://) falla por CORS. En local:  python3 -m http.server
   ============================================================ */

/**
 * Carga y VALIDA el turno. Si algo falta, lanza un error con
 * mensaje claro en vez de dejar la pantalla en blanco.
 */
export async function cargarTurno(url = "./data/turno.json") {
  let res;
  try {
    res = await fetch(url);
  } catch (e) {
    throw new Error(
      `No se pudo cargar ${url}. Si estas abriendo el fichero con doble clic, ` +
      `esto es lo esperado: sirve la carpeta por HTTP (python3 -m http.server).`
    );
  }
  if (!res.ok) throw new Error(`No se pudo cargar ${url} (HTTP ${res.status}).`);

  const d = await res.json();
  validar(d);
  return d;
}

function validar(d) {
  const faltan = [];
  if (!d || typeof d !== "object") throw new Error("turno.json no es un objeto.");
  if (!d.voluntario || typeof d.voluntario.alias !== "string") faltan.push("voluntario.alias");
  if (!Array.isArray(d.voluntario?.turno) || d.voluntario.turno.length !== 2) faltan.push("voluntario.turno");
  if (typeof d.puntos_base !== "number") faltan.push("puntos_base");
  if (!Array.isArray(d.misiones) || d.misiones.length === 0) faltan.push("misiones");

  if (faltan.length) {
    throw new Error("turno.json incompleto; falta: " + faltan.join(", "));
  }
  for (const m of d.misiones) {
    for (const k of ["orden", "t", "recogida", "centro", "raciones"]) {
      if (m[k] === undefined) throw new Error(`mision ${m.orden ?? "?"}: falta ${k}`);
    }
    /* El mensaje no es obligatorio: la tarjeta tiene una frase de respaldo.
       Pero si viene, tiene que ser texto usable y no un hueco en blanco. */
    if (m.mensaje !== undefined
        && (typeof m.mensaje !== "string" || !m.mensaje.trim())) {
      throw new Error(`mision ${m.orden ?? "?"}: mensaje vacio o no es texto`);
    }
  }
}
