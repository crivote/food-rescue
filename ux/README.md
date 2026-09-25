# La app del voluntariado — propuesta de interfaz

Prototipo de la interfaz que vería una persona voluntaria de **food-rescue** durante
un turno de recogida y entrega de comida. Se publica como web estática:

**https://crivote.github.io/food-rescue/ux/**

- `?modo=lamina` — las cuatro pantallas en fila (vista de diseño)
- sin parámetro — la app navegable, con el recorrido completo

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
  nombre inventado.
- **El nombre de la voluntaria**: *Juana España*, siguiendo la convención de los
  documentos de identidad de muestra.
- **El plano del trayecto**: es una **ilustración**, no una proyección del escenario.
  Las chinchetas están colocadas de forma verosímil para que se entienda el recorrido,
  pero **no corresponden a las coordenadas reales** de los puntos.

### Por qué esta separación

El objetivo del prototipo es enseñar **cómo se sentiría el turno**, no demostrar
geometría. Los números se mantienen fieles porque hacen la demo verificable; el
escenario visual es ilustrativo porque un plano realista de Madrid situaría comercios
inventados en calles reales. Se prefiere decir esto abiertamente antes que dejar la
duda.

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
2. **Ninguna palabra de ingeniería.** Ni "motor", ni "algoritmo", ni "optimización".
   Comprobable: `grep -iE "motor|algoritmo|haversine" ux/index.html`
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
    pantallas.js       las 4 pantallas — ÚNICA FUENTE del marcado
    nombres.js         id -> nombre legible (la frontera del punto 1)
    mapa.js            el plano y sus marcadores
    panel.js           panel inferior deslizable
    cabecera.js        barra de estado + menú
    data.js            carga y valida los datos
    tiempo.js          minutos del escenario -> horas de reloj
    gamificacion.js    puntos, niveles, objetivos
  data/turno.json      la traza real (generada, no escrita a mano)
  assets/              logo y plano
  build_turno.py       regenera data/turno.json desde el motor
```

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
