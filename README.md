# ROUTEOPT-AGENT

Implementación (Fase 2) del agente de optimización de rutas de entrega del documento de diseño inicial.
Curso de Inteligencia Artificial, Universidad Tecnológica de Bolívar.

Agente **basado en utilidad con aprendizaje** (Russell y Norvig) que, cada 5 minutos simulados, percibe el
estado de una flota de repartidores, decide si conviene (re)planificar comparando alternativas con una función
de utilidad y actúa enviando rutas a los repartidores. Todo corre sobre un **simulador** del entorno.

## Requisitos y ejecución

Python 3.10 o superior. Sin APIs de pago ni claves.

```bash
git clone <URL-del-repositorio> && cd routeopt-agent
python -m venv .venv && source .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest -q                                              # 8 pruebas automáticas
python -m routeopt --days 10 --out results             # 10 jornadas: agente vs. planificación manual
python -m routeopt --days 10 --ablations --out results # añade variantes sin aprendizaje / sin replanificación
python -m routeopt --days 10 --windows 30,45,60 --out results_estrechas   # ventanas de tiempo más estrechas
```

Tarda entre 20 y 60 segundos. Resultados en `results/`:

- `metricas_por_jornada.csv`: medidas de desempeño por jornada y variante.
- `resumen.json`: reducción de distancia, % a tiempo, etc. frente a la línea base.
- `logs/<variante>_diaNN.jsonl`: **log de ejecución** (percepciones, decisiones, acciones y resultados, con marca
  de tiempo real `ts` y simulada `sim_hhmm`). Ejemplo en `docs/ejemplo_log_routeopt_dia03.jsonl`.
- `memoria_routeopt.json`: lo aprendido por el agente (perfil de tráfico y tiempos de atención).

Todo es reproducible: el escenario de cada jornada es función de `(--seed, día)`.

## Dónde está cada cosa (ciclo percepción → decisión → acción)

| Parte del ciclo | Código |
|---|---|
| Bucle del ciclo | `routeopt/runner.py::run_day` (observe → `agent.step` → apply) |
| Función del agente | `routeopt/agent.py::RouteOptAgent.step` = `_perceive` → `_decide` → `_act` |
| Percepción (sensores) | `env.py::Env.observe` genera el `Percept`; `agent.py::_perceive` actualiza el modelo |
| Decisión | `agent.py::_decide` (disparadores) y `_plan` (inserción más barata + búsqueda local) |
| Función de utilidad | `agent.py::_cost` y `_utility` |
| Acción (actuadores) | `agent.py::_act` emite `AssignRoute` y `Notify`; `env.py::Env.apply` los ejecuta |
| Estado interno (basado en modelo) | `_start_day`, `_perceive`: pedidos, distancias, `dev` (tráfico actual), colas |
| Aprendizaje | `_perceive` (tiempos de atención) y `end_day` (perfil de tráfico entre jornadas) |
| Entorno simulado | `routeopt/env.py::Scenario` y `Env` |
| Línea base manual | `routeopt/baselines.py` |
| Log | `routeopt/logger.py` |

**Utilidad:** `U(plan) = −(w_dist·km + w_late_min·min_tarde + w_late_stop·n_tarde + w_load·horas²)`, evaluada
con el modelo interno del agente (tráfico esperado, tiempos de atención aprendidos). Parámetros en `config.py`.

**Disparadores de replanificación:** incidente de un repartidor, pedidos sin asignar (obligatorios);
repartidor que vuelve a estar disponible, o retraso previsto mayor a 8 min (opcionales; solo se aplican si
mejoran la utilidad en más de `replan_eps` y respetan un intervalo mínimo de 15 min, por estabilidad).

## Qué hace el código y qué hacen las herramientas externas

| Función del diseño | En esta implementación |
|---|---|
| Razonamiento (utilidad, búsqueda, replanificación) | Código propio en Python (`agent.py`). Sin librerías de optimización. |
| Aprendizaje | Código propio: medias móviles de tráfico por zona/franja y de tiempos de atención por zona. |
| Sistema de pedidos, GPS, API de tráfico, app del repartidor | **Simulados** en `env.py` (el agente solo ve el `Percept`). |
| Cálculo numérico | `numpy` (solo en el simulador para generar números aleatorios). |
| LLM | **No se usa.** Ninguna decisión depende de un modelo de lenguaje. |

## Cambios respecto al diseño (también documentados en `docs/seccion_implementacion.md`)

1. Los sensores y actuadores externos se simulan (el diseño asume sistemas reales).
2. El tiempo se discretiza en ciclos de 5 min; las variables siguen siendo continuas.
3. La función de utilidad incorpora un término de carga de trabajo por repartidor (`w_load`), que el diseño
   no explicitaba. Sin él, el agente concentraba casi todos los pedidos en un solo repartidor.
4. El aprendizaje usa estimadores simples (medias móviles), no aprendizaje por refuerzo como DeliverAI.
5. La "planificación manual actual" no existe como dato; se modela con un despachador simulado
   (`ManualZonal`). Si hay rutas manuales reales, hay que reemplazar esa línea base.

## Resultados preliminares (10 jornadas simuladas, semilla 2026)

| Ventanas de tiempo | Reducción de distancia vs. manual zonal | Peor jornada | % a tiempo (agente / manual) |
|---|---|---|---|
| 60 a 120 min | 28,6 % | 14,2 % | 99,5 / 100,0 |
| 30 a 60 min | 21,2 % | 9,3 % | 100,0 / 98,8 |

Lectura honesta de estos números:

- La meta SMART (≥ 15 % en promedio) se cumple en el simulador, pero **1 de 10 jornadas queda por debajo**
  con ventanas anchas y 3 de 10 con ventanas estrechas. El resultado depende de la línea base elegida y de los
  supuestos del simulador; no equivale a una prueba con operación real.
- En el simulador **no se demuestra** que la replanificación ayude (la variante sin replanificación obtuvo
  igual o mayor reducción). Los incidentes son poco frecuentes (25 % por repartidor y jornada). El aprendizaje
  sí mejora el % a tiempo con ventanas estrechas (100,0 % frente a 97,5 % sin aprendizaje), con solo 10 jornadas.
- El agente atiende más tarde dentro de cada ventana (demora media desde la apertura de la ventana: 24 min frente
  a 6 min del manual con ventanas anchas), porque agrupa paradas cercanas. Es coherente con la utilidad, pero
  debe reportarse como compromiso, no ocultarse.
- La carga queda desbalanceada (en promedio 13,6 paradas el repartidor más cargado y 6,9 el menos cargado,
  frente a 10 y 10 del manual).

## Limitaciones

Simulador propio con supuestos fijados por el equipo (ver `config.py`); sin red vial real (distancia euclidiana
por factor de 1,3); sin horario de turno ni capacidad de carga; los pedidos son conocidos al inicio de la jornada.
