# Borrador: sección nueva para el documento de diseño

Este borrador está en tercera persona y tono formal para pegarlo en el documento. Los datos entre
corchetes deben completarse con la URL real del repositorio.

---

## 10. Implementación del agente

### 10.1 Alcance y arquitectura

ROUTEOPT-AGENT se implementó en Python 3 como un agente basado en utilidad con aprendizaje, conforme al diseño
inicial. El repositorio [URL] contiene el simulador del entorno, el agente, la línea base de planificación
manual, el registro de ejecución y las pruebas automáticas. La función del agente se encuentra en la clase
`RouteOptAgent` (`routeopt/agent.py`) y se ejecuta en un ciclo explícito de percepción, decisión y acción:

- **Percepción** (`Env.observe` y `RouteOptAgent._perceive`): el agente recibe lista de pedidos, posición y
  disponibilidad de cada repartidor, estimación de tráfico por zona y entregas terminadas. Con ello actualiza
  su modelo interno: matriz de distancias, desviación del tráfico actual respecto de lo esperado y estado de
  las colas de cada repartidor.
- **Decisión** (`_decide`, `_plan`, `_utility`): evalúa la utilidad del plan vigente y, ante un disparador,
  genera alternativas mediante inserción más barata y búsqueda local (reubicación, 2-opt e intercambio entre
  rutas). Selecciona la alternativa de mayor utilidad.
- **Acción** (`_act`, `Env.apply`): envía a cada repartidor su nueva secuencia de paradas (`AssignRoute`) y una
  notificación (`Notify`).

La función de utilidad es U(plan) = −(w_dist·km + w_late_min·minutos de retraso + w_late_stop·paradas tardías +
w_load·horas de trabajo²), calculada con tiempos de viaje esperados a partir del perfil de tráfico aprendido y
corregido por el sensor actual.

### 10.2 Entorno simulado

El entorno real no está disponible, por lo que se construyó un simulador (`routeopt/env.py`) que genera las
percepciones de la sección 5 y respeta las propiedades de la sección 3:

| Propiedad (sección 3) | Cómo se respeta en el simulador |
|---|---|
| Parcialmente observable | El agente solo percibe un sensor de tráfico con ruido; el tráfico real y los tiempos de atención reales permanecen ocultos hasta que ocurre la entrega. |
| Estocástico | Ruido lognormal en tiempos de viaje y atención, congestiones repentinas por zona e incidentes de repartidores. |
| Secuencial | La hora de llegada a cada parada depende de las paradas anteriores. |
| Dinámico | El tráfico evoluciona con el reloj, con horas pico, independiente de las acciones del agente. |
| Continuo | Posiciones, distancias y tiempos son reales; el ciclo de decisión se discretiza cada 5 minutos. |
| Varios repartidores | Flota de cuatro repartidores coordinada por un único agente de software. |

Cada jornada es función de una semilla, por lo que dos agentes distintos enfrentan exactamente el mismo
escenario y pueden compararse de forma pareada.

### 10.3 Reparto del razonamiento entre el código y las herramientas externas

Todo el razonamiento (utilidad, búsqueda, replanificación y aprendizaje) lo ejecuta código propio. No se
emplean modelos de lenguaje, librerías de optimización ni servicios de pago. Los servicios externos del diseño
(sistema de pedidos, GPS, API de tráfico y aplicación del repartidor) se sustituyen por el simulador. La
librería `numpy` se usa únicamente para generar números aleatorios reproducibles.

### 10.4 Aprendizaje

El agente mantiene dos memorias de largo plazo que persisten entre jornadas: el perfil de tráfico esperado por
zona y franja de 30 minutos (media móvil de lo observado por el sensor) y el tiempo medio de atención por zona
(media móvil de los tiempos observados). Ambas corrigen sus estimaciones de llegada y por tanto la utilidad de
cada alternativa.

### 10.5 Cambios respecto al diseño inicial y su justificación

1. **Sensores y actuadores simulados.** No se dispone de una flota ni de APIs reales.
2. **Discretización temporal de 5 minutos.** Necesaria para ejecutar el ciclo de percepción y acción; las
   variables del entorno continúan siendo continuas.
3. **Término de carga de trabajo en la utilidad.** En una primera versión la utilidad solo penalizaba distancia
   y retrasos, y el agente concentraba hasta 22 de 40 pedidos en un repartidor. Se añadió un costo convexo por
   horas de trabajo para repartir la carga, coherente con la utilización de flota de la sección 7.
4. **Aprendizaje con estimadores simples.** El diseño menciona DeliverAI como referencia de aprendizaje por
   refuerzo; la implementación usa medias móviles, más sencillas de verificar con el tiempo disponible.
5. **Línea base manual simulada.** El diseño no define la "planificación manual actual". Se modeló un
   despachador que reparte por sectores angulares alrededor del depósito y ordena por hora de apertura de la
   ventana, sin reajustar durante la jornada.

### 10.6 Registro de ejecución y reproducibilidad

Cada ejecución genera un archivo JSON Lines por jornada con percepciones, decisiones, acciones y resultados,
cada uno con marca de tiempo real y simulada. El repositorio incluye `requirements.txt`, instrucciones de
ejecución en el `README.md` y ocho pruebas automáticas.

---

# Correcciones sugeridas al documento original (secciones 1 a 9)

Estas son las inconsistencias que encontré al contrastar el documento de diseño con la implementación.
Conviene que ustedes decidan cuáles aplicar.

1. **Sección 3, número de agentes.** El documento dice "Multiagente", pero en el diseño existe un único agente
   de software que asigna rutas de forma centralizada; los repartidores son actores humanos que ejecutan.
   Según el criterio de AIMA, lo más coherente es "agente único con coordinación centralizada de varios
   repartidores" (como hace el documento de InjuryShield con el cuerpo técnico). Si se mantiene "multiagente",
   debe justificarse qué agentes autónomos hay.
2. **Sección 3, discretización.** Dice "Continuo". Las variables lo son, pero el ciclo de decisión y el conjunto
   de paradas son discretos. Conviene "continuo en variables, discreto en el ciclo de decisión".
3. **Sección 7, indicadores sin fórmula ni umbral.** El % de entregas en ventana, el tiempo promedio de entrega,
   las replanificaciones y la utilización de flota no tienen fórmula ni umbral. Sin ellos no se pueden probar de
   forma objetiva en la Fase 3. Propuesta mínima: % a tiempo ≥ 95 % y no menor que el de la línea base;
   utilización = (minutos de viaje + atención) / duración de la jornada.
4. **Sección 7, línea base.** Definir qué es "planificación manual" (ver 10.5, punto 5) y quién la proveyó.
   Si el equipo tiene rutas reales, usarlas.
5. **Sección 7, "tiempo promedio de entrega".** Es ambiguo. En la implementación se reporta la demora desde
   la apertura de la ventana, y el agente la aumenta al agrupar paradas. Hay que definir la medida y aceptar
   o no ese compromiso.
6. **Sección 8, aprendizaje.** El documento sugiere modelos predictivos y cita aprendizaje por refuerzo;
   la implementación solo aprende promedios. Ajustar el texto al alcance real.
7. **Sección 5, entradas.** Indica API de mapas y tráfico en tiempo real; en la implementación son simuladas.
   Dejar claro en la sección 10 qué es real y qué es simulado (ya cubierto arriba).
