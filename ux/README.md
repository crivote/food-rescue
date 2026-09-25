# La app del voluntariado de NextFood — propuesta de interfaz

Prototipo de la interfaz que vería una persona voluntaria de **NextFood** durante
un turno de recogida y entrega de comida. Se publica como web estática:

**https://crivote.github.io/food-rescue/ux/**

- `?modo=lamina` — las seis pantallas en fila (vista de diseño)
- sin parámetro — la app navegable, con el recorrido completo

La marca (**NextFood**, hoja que se vuelve cesta) es una propuesta de nombre para el
producto; el repositorio conserva el nombre del reto (`food-rescue`). El logotipo vive
en `assets/logo_trans.png` y su favicon (`assets/favicon.ico`) se deriva del icono.

---

## Para quien evalúa: qué es real y qué no

Es la pregunta importante, así que va primero y sin rodeos.

### Es real

- **Todo el turno.** Las 4 misiones, su orden, las raciones de cada recogida y las horas
  de caducidad salen de **una traza real del motor** sobre el escenario simulado
  `sample_01`, corriendo el asignador del entregable. No hay cifras decorativas.
- **El reparto del turno: 18 + 18 + 18 + 20 = 74 raciones**, y los puntos (260 → 1000)
  son la consecuencia aritmética de esas raciones.
- **Los kilómetros y minutos** de cada tramo se calculan con la misma fórmula y la misma
  velocidad que usa el simulador.
- **El escenario simulado** reproduce la geometría de Madrid (coordenadas reales) y la
  dificultad del problema del reto.

### Es ficticio

- **Los nombres de los comercios y de los centros de entrega** (*Supermercado El
  Huerto*, *Comedor La Concordia*...), y sus direcciones. Los puntos del escenario son
  identificadores internos (`r32`, `c5`); para que la pantalla sea legible se les da un
  nombre inventado. **Importante:** un punto `c` es siempre **destino** en el modelo
  (`recogidas` y `centros` son las dos únicas clases de punto, y el centro es el que
  tiene capacidad de almacenaje), así que su nombre tiene que sonar a destino que
  recibe, no a comercio que entrega. Por eso *c3* es un **banco de alimentos**, no un
  centro vecinal: el nombre viejo contradecía el papel del punto en el turno.
- **El nombre de la voluntaria**: *Juana España*, siguiendo la convención de los
  documentos de identidad de muestra.
- **El plano del trayecto**: es una **ilustración generada**, no una proyección del
  escenario. Las chinchetas están colocadas de forma verosímil para que se entienda el
  recorrido, pero **no corresponden a las coordenadas reales** de los puntos. Se eligió
  la variante sin ningún texto incrustado, para que los rótulos de la interfaz sean los
  únicos que se leen (y se puedan cambiar sin rehacer la imagen).
- **Las fotos de los locales**: son **imágenes generadas**, no fotografías de los
  comercios reales (que no existen: los puntos del escenario son simulados). Hacen la
  función de «así reconocerás el sitio al llegar». El nombre del fichero es el del
  **local inventado**, nunca el identificador del escenario, para que el repositorio
  público no revele la nomenclatura interna.
- **El retrato de la voluntaria**: también es una imagen generada, no una persona real.

### Qué punto tiene foto y cuál no

Hay foto de **los 6 puntos**: los 4 comercios de recogida (supermercado, panadería,
frutería, restaurante) y los 2 centros de entrega (comedor y banco de alimentos). La
foto aparece en la pantalla de llegada, que es donde el voluntario necesita confirmar
que está en el sitio correcto, y el pie cambia según el momento: *"Así reconocerás el
local"* al recoger, *"Así reconocerás el punto de entrega"* al entregar.

Cuando un punto no tiene foto **no se pinta nada**: un hueco ausente es mejor que una
imagen rota o una de relleno. Añadir una foto es solo dejar el fichero en `assets/` y
nombrarlo en el diccionario.

### Por qué esta separación

El objetivo del prototipo es enseñar **cómo se sentiría el turno**, no demostrar
geometría. Los números se mantienen fieles porque hacen la demo verificable; el
escenario visual es ilustrativo porque un plano realista de Madrid situaría comercios
inventados en calles reales. Se prefiere decir esto abiertamente antes que dejar la
duda.

---

## Cómo se integra con el solver

La app es la **capa de producto** del mismo motor que resuelve el reto. No hay dos
lógicas: `data/turno.json` sale de ejecutar el motor real, y la interfaz solo presenta su
resultado.

```
solver_match_crit.py  (el motor determinista, base de la entrega)
        │
        │  simulate.py --solver solver_match_crit.py --registro traza.json
        ▼
   traza del simulador  ──►  build_turno.py  ──►  data/turno.json  ──►  la interfaz
        (registro real)         (extrae el           (la única
                                 turno de un           fuente de datos)
                                 voluntario)
```

> Nota: la entrega del reto es el solucionador unificado `ml/solver_scorer.py`
> (scorer + guardrail, 58.5% en el escenario publicado). El prototipo de `ux/`
> se genera con el **motor determinista** (`solver_match_crit.py`, 55.4%) porque
> corre con la biblioteca estándar, sin dependencias. La traza de la app es real
> en ambos casos; se eligió el motor por simplicidad de reproducción del
> prototipo, no porque sea el solucionador de la entrega.

**Qué es exactamente lo que se copia de la traza.** `build_turno.py` recorre el registro
del simulador, se queda con las misiones del voluntario objetivo y deriva:

- las 4 recogidas, su orden, las raciones de cada una y su hora de caducidad → tal cual
  de la traza;
- los km y minutos de cada tramo → recalculados con la **misma fórmula haversine y la
  misma velocidad** que usa el simulador (`velocidad_kmh` del voluntario), no estimados;
- la capacidad y la ventana del turno → del escenario.

Los dos únicos valores que **no** salen del motor son el alias y la foto de la
voluntaria, que son presentación. Están marcados como tal en el propio script.

### La frontera: `js/nombres.js`

El motor razona con identificadores (`r32`, `c5`) y un centro `c` es siempre **destino**
(el que tiene capacidad de almacenaje), nunca un comercio. Esos identificadores son
andamiaje interno y no pueden aparecer en pantalla. `js/nombres.js` es la frontera única:
todo lo que se muestra pasa por `nombreDe()`, y si un punto no está en el diccionario
devuelve una descripción genérica legible, **jamás el identificador crudo**.

Las fotos se nombran por el **local inventado** (`supermercado-huerto.webp`), nunca por
el identificador del escenario, para que el repositorio público no revele la
nomenclatura interna. La correspondencia real está solo en `nombres.js`.

### Qué NO hace la interfaz

- **No decide nada.** No hay asignación, ni optimización, ni reasignación en la app. El
  turno que se ve es el que decidió el motor, y la interfaz no puede cambiarlo.
- **No llama al motor en vivo.** Es un prototipo de interacción sobre una traza
  precalculada, no un cliente del `decidir(estado)` en ejecución.
- **No está conectada a ningún servicio externo.** No hay red, ni backend, ni API. La
  página es HTML, CSS y JS servidos como ficheros estáticos.

El salto a producto es sustituir la traza por la respuesta en vivo de `decidir(estado)`:
la forma de los datos no cambia, solo quién los produce.

---

## Decisiones de diseño

Estas son las que costaron una vuelta, y por qué quedaron así:

- **Seis pantallas, no cuatro.** El stepper anuncia cuatro pasos y ahora los cuatro se
  alcanzan. Se añadieron las dos que faltaban (el viaje al centro y el cierre en la
  entrega) porque el recorrido de vuelta existe en los datos y no se estaba contando.
- **Cargado ≠ entregado.** La caja sale del comercio con N raciones, pero por el camino
  algo puede estropearse o el centro puede rechazar producto deteriorado. Los puntos se
  suman al **cerrar la entrega**, contando lo que el centro **acepta**, con tope en lo
  cargado. Si hay diferencia, la pantalla de recompensa lo explica sin dramatizar.
- **La foto va en la pantalla de llegada**, no en la de camino (que ya lleva el plano).
  Ahí es donde sirve: para confirmar que se está en el sitio correcto. El pie cambia
  según el momento (*"Así reconocerás el local"* / *"…el punto de entrega"*).
- **El plano es ilustrativo, los números no.** El fondo es una ilustración generada y las
  chinchetas están colocadas de forma verosímil, no proyectadas desde las coordenadas
  reales. Un plano realista de Madrid situaría comercios inventados en calles reales.
- **El mensaje de la misión lo escribe un LLM, con datos del turno.** La tarjeta de
  misión no lleva una frase fija: `build_mensajes.py` reproduce el turno tick a tick con
  el motor real, arma un **contexto por misión** (raciones, margen de tiempo, recorrido,
  `n_cap` real de ese tic, minutos que lleva de turno, entregas hechas, raciones salvadas,
  objetivo del turno y los puntos que le faltan para subir de nivel) y lo traduce con
  gemma a una frase cercana. El resultado se guarda en `data/turno.json` junto a su
  contexto, así que la frase es **auditable**: se puede comprobar de qué datos salió.
  `n_cap` no es una estimación: el motor lo computa al decidir (`_criticidad`) pero no lo
  exporta, así que se recalcula con esa misma función durante el replay. Sin LLM
  disponible cae a una plantilla determinista que usa los mismos datos; la tarjeta nunca
  queda sin texto. El LLM **no** decide nada: el turno ya está fijado por el motor.
- **El reloj del turno avanza paso a paso.** La hora de cada misión (`t` en los datos)
  es la de su **salida**, un valor fijo: si el panel se quedara ahí, el turno restante y
  la barra temporal solo se moverían al cerrar cada entrega. Con los minutos de cada
  tramo —que ya vienen en los datos— el reloj avanza al llegar al comercio y al llegar
  al centro, así que el voluntario ve su tiempo restante bajar mientras trabaja. Se
  cuenta **solo el recorrido**, sin inventar minutos de carga o descarga: la traza real
  deja 1 min de holgura entre la misión 3 y la 4, y cualquier margen añadido al alza
  haría que una misión arrancase antes de que cerrase la anterior. Verificado sobre el
  turno completo: el reloj no retrocede nunca y cierra a las 21:27, con los 108 min de
  camino de la traza real.
- **Puntos y nivel se derivan, no se acumulan.** `estado.js` los calcula de las raciones
  entregadas, así que no pueden desincronizarse del contador.
- **La pantalla final también deriva.** `pantallaExito` saca las raciones de esta entrega
  y la subida de nivel del propio estado, no de parámetros. Cuando los recibía por
  parámetro, el repintado del último paso los perdía y la pantalla que cierra el turno
  salía con «undefined raciones» y «+NaN pts» —justo la última que ve quien evalúa—. La
  comparación de nivel se calcula además con la tabla real de niveles: con un umbral fijo
  de 900 puntos no se celebraba pasar de *Colaboración* a *Voluntariado*. Se añadió
  `cerrarTurno()` porque el repintado sustituye el nodo del botón: marcar `disabled` a
  mano se deshacía y el clic parecía no hacer nada.
- **Los niveles son neutros en género** (*Primeros pasos*, *Colaboración*,
  *Voluntariado*, *Rescate*, *Líder de turno*) porque la interfaz no debe presuponer
  quién la usa.

---

## Principio de diseño

**Quien usa esto no es quien lo evalúa.** La persona voluntaria no sabe —ni tiene por
qué saber— que detrás hay un sistema que decide asignaciones. La interfaz tiene tres
trabajos: dar información clarísima, guiar el siguiente paso y devolver una recompensa
emocional por el esfuerzo.

De ahí tres reglas que el código respeta y que se pueden comprobar:

1. **Ningún identificador interno llega a la pantalla.** `js/nombres.js` es la frontera:
   todo lo que se muestra pasa por ahí, y si un punto no está en el diccionario
   devuelve una descripción genérica legible, **nunca el identificador crudo**.

   ```bash
   # los unicos ids viven en la tabla de nombres, que es donde deben estar
   grep -rE "\b[rc][0-9]{1,3}\b" index.html js/ css/     # -> solo js/nombres.js
   ```

2. **Ninguna palabra de ingeniería.** Ni "motor", ni "algoritmo", ni "optimización".
   El texto que ve el usuario está en `js/`, no en el HTML:

   ```bash
   grep -riE "motor|algoritmo|haversine|optimizaci" index.html js/ css/ data/
   # -> sin resultados
   ```

3. **El lenguaje de la recompensa es emocional.** Puntos, nivel y objetivo del turno.

---

## Estructura

```
ux/
  index.html           solo estructura + el sprite de iconos
  css/
    tokens.css         paleta y variables (único sitio con colores)
    layout.css         el teléfono, la pantalla, los modos app/lámina
    components.css     tarjetas, botones, plano, panel, stepper
  js/
    app.js             arranque y flujo del turno
    estado.js          estado en memoria; puntos y nivel DERIVADOS
    pantallas.js       las 6 pantallas — ÚNICA FUENTE del marcado
    nombres.js         id -> nombre legible (la frontera del punto 1)
    mapa.js            el plano y sus marcadores
    panel.js           panel inferior deslizable
    cabecera.js        barra de estado + menú
    data.js            carga y valida los datos
    tiempo.js          minutos del escenario -> horas de reloj
    gamificacion.js    puntos, niveles, objetivos
  build_turno.py       regenera data/turno.json desde el motor
  build_mensajes.py    escribe el mensaje de cada misión (LLM + contexto)
  data/turno.json      la traza real (generada, no escrita a mano)
  assets/              marca (logo + favicon), plano y fotos de los locales
```

Las fotos se sirven a 640 px de ancho en webp (27-65 KB cada una) y el CSS las recorta a
132 px de alto.

**`pantallas.js` es la única fuente del marcado.** Tanto la app navegable como la vista
de lámina componen las mismas funciones; sólo cambia el contenedor. Duplicar el marcado
es la forma segura de que los dos modos se desincronicen al primer cambio.

---

## Cómo ejecutarlo en local

Los datos se cargan con `fetch()` y el código son módulos ES, así que **hace falta
servirlo por HTTP**: abrir `index.html` con doble clic no funciona (el navegador bloquea
las peticiones desde `file://`). Es esperado, no un fallo.

```bash
cd ux
python3 -m http.server 8000
# abre http://localhost:8000/
```

## Regenerar los datos del turno

```bash
cd ux
python3 build_turno.py
```

Corre el motor sobre el escenario y reescribe `data/turno.json`. Si las cifras cambian,
al volver a cargar la página cambian solas: la interfaz no tiene ningún dato escrito a
mano.

---

## Estado y alcance

Es un **prototipo de interacción** para la demostración del MVP. Lo que demuestra es el
aspecto y el flujo; no es la aplicación final ni está conectada a ningún servicio real.

Los **datos del turno son reales** (salen del motor), pero el turno que se ve es **una
traza precalculada**, no una ejecución en vivo del motor. Y el flujo se recorre con
botones: no hay backend, ni cuentas, ni estado que sobreviva a recargar la página.
