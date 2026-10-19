# Fase 3: pruebas contra las medidas de desempeño

## 1. Diseño de las pruebas

**Qué se fijó antes de ejecutar.** Las fórmulas, los umbrales, los escenarios aplicables y el criterio de
cumplimiento están en `pruebas/umbrales.json`, escrito antes de correr `pruebas/run_fase3.py`. Aclaración de
transparencia: ese archivo se escribió después de haber visto los resultados preliminares de la Fase 2, así que los
umbrales parten de criterios de servicio y del diseño, no de un ajuste sobre los resultados de esta fase. Las
pruebas usan semillas distintas (101 a 105) de las usadas al desarrollar (2026).

**Repeticiones.** 12 escenarios × 5 repeticiones × 10 jornadas simuladas. Cada repetición es un bloque de 10
jornadas (dos semanas hábiles) con semilla propia y un agente nuevo. Se reporta media y desviación estándar entre
repeticiones.

**Criterio de cumplimiento por escenario.** La media de las 5 repeticiones cumple el umbral y al menos 4 de 5
repeticiones lo cumplen. M6 y M7 exigen 100 % en las 5.

| Tipo | Escenario | Qué prueba |
|---|---|---|
| Normal | N1_base | 40 pedidos, 4 repartidores, ventanas de 60 a 120 min |
| Normal | N2_ventanas_estrechas | ventanas de 30 a 60 min |
| Normal | N3_volumen_alto | 60 pedidos |
| Normal | N4_volumen_bajo | 16 pedidos |
| Normal | N5_flota_reducida | 2 repartidores |
| Límite | L1_un_repartidor | 1 repartidor, 20 pedidos |
| Límite | L2_un_pedido | 1 solo pedido |
| Límite | L3_ventanas_extremas | ventanas de 15 a 30 min |
| Adverso | A1_congestion_total | congestión repentina en las 9 zonas |
| Adverso | A2_incidentes_totales | los 4 repartidores sufren un incidente |
| Falla esperada | F1_sensor_sin_dato | la API de tráfico no entrega ningún dato |
| Falla esperada | F2_entradas_invalidas | 3 pedidos inválidos: ventana invertida, fuera de la ciudad y coordenada faltante |

## 2. Medidas reformuladas respecto al documento de diseño

| Medida original (sección 7) | Problema | Medida probada |
|---|---|---|
| Reducción ≥ 15 % en dos semanas de operación real | No hay operación real ni línea base manual definida | M1: 10 jornadas simuladas contra el despachador manual zonal (`routeopt/baselines.py`) |
| % de entregas en ventana | Sin umbral | M2, umbral ≥ 95 % |
| Tiempo promedio de entrega | Ambigua y sin umbral | M3: demora media desde la apertura de la ventana, ≤ 30 min |
| Cantidad de replanificaciones | Sin umbral | M4: ≤ 3 por jornada (estabilidad) |
| Utilización de la flota | Menos distancia baja la utilización por construcción, así que premia lo contrario de M1 | M5: balance de carga, paradas del más cargado / promedio ≤ 1,5 |
| (no existía) | El diseño exige manejar datos incompletos (sección 4) | M6 robustez y M7 detección de entradas inválidas |

## 3. Tabla de resultados (obligatoria)

La columna de resultados agrupa todas las repeticiones de los escenarios aplicables (media ± desviación estándar,
y entre paréntesis el rango de las medias por escenario). El detalle por escenario está en la sección 5.

| Medida de desempeño | Fórmula | Umbral | Casos ejecutados | Resultado obtenido | ¿Cumple? | Evidencia |
|---|---|---|---|---|---|---|
| M1. Reducción de distancia vs. manual | 100·(1 − km agente / km manual), 10 jornadas | ≥ 15 % | 9 escenarios × 5 rep. × 10 jornadas = 450 | 28,1 ± 6,2 % (19,6 a 37,4; peor repetición 16,3) | **Sí**, 9/9 | `pruebas/resultados/resumen_por_escenario.csv`; log `pruebas/logs/N1_base_rep1_dia01.jsonl`; video min __ |
| M2. Entregas dentro de ventana | 100·llegadas ≤ cierre / entregas | ≥ 95 % | 10 × 5 × 10 = 500 | 98,4 ± 1,5 % (95,7 a 100,0) | **Parcial**, 9/10 (falla L1: 95,7 %, solo 3/5 repeticiones) | CSV anterior; log `L1_un_repartidor_rep1_dia01.jsonl`; video min __ |
| M3. Demora media desde apertura de ventana | media de (inicio de atención − apertura) | ≤ 30 min | 10 × 5 × 10 = 500 | 18,3 ± 10,8 min (0,5 a 32,5) | **Parcial**, 8/10 (fallan N5: 30,1 y L1: 32,5) | CSV; logs `N5_flota_reducida_...`, `L1_un_repartidor_...`; video min __ |
| M4. Replanificaciones por jornada | media de replanificaciones aceptadas | ≤ 3 | 10 × 5 × 10 = 500 | 1,9 ± 1,6 (0 a 5,9) | **Parcial**, 9/10 (falla A2: 5,9, 0/5 repeticiones) | CSV; log `A2_incidentes_totales_rep1_dia01.jsonl`; video min __ |
| M5. Balance de carga | paradas del más cargado / (pedidos / repartidores) | ≤ 1,5 | 8 × 5 × 10 = 400 | 1,32 ± 0,14 (1,13 a 1,58) | **Parcial**, 7/8 (falla N4: 1,58, 2/5 repeticiones) | CSV; log `N4_volumen_bajo_rep1_dia01.jsonl`; video min __ |
| M6. Robustez (jornadas sin excepción) | 100·jornadas terminadas / ejecutadas | 100 % | 12 × 5 × 10 = 600 | 91,7 % (11 escenarios al 100 %, F2 al 0 %) | **No**, 11/12 | `resultados_por_repeticion.csv` (columna `errores`: ValueError); log `F2_entradas_invalidas_rep1_dia01.jsonl`; video min __ |
| M7. Detección de entradas inválidas | 100·inválidos reportados / inyectados | 100 % | 1 × 5 × 10 = 50 | 0 % (0 de 3 detectados en las 5 repeticiones) | **No** | mismo log y CSV; video min __ |

La columna "video min" debe completarse cuando el equipo grabe la demostración.

## 4. Análisis de resultados

**Qué se cumplió.** La medida principal (M1) se cumplió en los 9 escenarios aplicables, incluso en los adversos
(28,1 ± 6,2 %; peor repetición 16,3 %). El agente también se mantuvo estable (M4, 1,9 replanificaciones por jornada)
y razonablemente balanceado (M5) en casi todos los casos. Este resultado vale solo para el simulador y para la línea
base elegida, que es un proxy de despachador manual; no equivale a operación real.

**Qué no se cumplió, causa probable y cambio propuesto.**

1. **M6 y M7 (F2, entradas inválidas): la falla más grave.** Las 50 jornadas terminaron en `ValueError`: una sola
   coordenada faltante tumba la planificación de toda la flota, porque `_start_day` calcula la zona del pedido (`zone_of`) sin
   validarlo. Un diagnóstico aparte (fuera de la tabla pre-registrada) mostró que los otros dos pedidos inválidos
   no se detectan: el agente los atiende en silencio y el de las coordenadas fuera de la ciudad casi duplicó la
   distancia diaria (de unos 134 a unos 290 km). Cambio: validar los pedidos al ingreso, aislar los inválidos,
   registrar una alerta, exponerlos en `rejected_orders` y planificar el resto.
2. **M4 en A2 (5,9 frente a ≤ 3).** Con los 4 repartidores averiados, cada incidente y cada reincorporación
   disparan replanificación. Cambio: agrupar los disparos obligatorios que ocurren en el mismo ciclo y añadir un
   tiempo de espera entre replanificaciones por incidente. No se movió el umbral después de ver el resultado.
3. **M3 en N5 y L1 (30,1 y 32,5 min) y M2 en L1 (95,7 %).** Con 1 o 2 repartidores la flota queda saturada y las
   paradas se atienden más tarde dentro de la ventana. La utilidad no penaliza la demora mientras no haya retraso,
   así que el agente no la reduce. Cambio: añadir un costo por demora a la utilidad, y avisar al responsable
   logístico cuando la flota sea insuficiente para el volumen.
4. **M5 en N4 (1,58 frente a ≤ 1,5).** Con 16 pedidos y 4 repartidores el promedio es 4 y el máximo ronda 6; el
   término de carga (horas al cuadrado) pesa muy poco con volúmenes bajos. Cambio: escalar `w_load` con el volumen
   o penalizar la diferencia entre rutas.

**Hallazgo que contradice la expectativa.** F1 (sensor de tráfico sin dato) se planteó como falla esperada, pero el
agente casi no se degradó: 98,9 % a tiempo y 31,0 % de reducción, frente a 99,5 % y 31,7 % en N1. Es coherente con las
ablaciones de la Fase 2: en este simulador la información del sensor aporta poco. La prueba no demuestra que el agente
use el tráfico para adaptarse. Antes de afirmarlo en el documento habría que endurecer el simulador (congestión más
fuerte, ventanas más justas) y repetir F1.

**Limitaciones.** La línea base manual es un proxy; los escenarios y el tráfico son simulados. Los umbrales de M2 a M5 los
fijó el equipo sin un cliente real que los respalde.

## 5. Detalle por escenario

Ver `pruebas/resultados/tablas.md` (media ± desviación estándar, mínimo, máximo y repeticiones que cumplen).

## 6. Cómo reproducir

```bash
python -m pruebas.run_fase3     # ~12 min; es reanudable si se interrumpe (caché en pruebas/resultados/parcial)
```
