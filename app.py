"""Interfaz Streamlit para demostrar el agente ROUTEOPT."""
from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

from routeopt.agent import RouteOptAgent
from routeopt.baselines import ManualEDD, ManualZonal
from routeopt.config import Config
from routeopt.env import Scenario
from routeopt.runner import run_day


class MemoryLogger:
    def __init__(self):
        self.records = []

    def log(self, kind: str, sim_t: float, **data):
        self.records.append({"kind": kind, "sim_min": round(sim_t, 2), **data})

    def close(self):
        pass


st.set_page_config(page_title="ROUTEOPT | Centro de operaciones", page_icon="🛵", layout="wide")
st.markdown(
    """
    <style>
    .stApp, [data-testid="stSidebar"] {
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
            "Segoe UI Emoji", "Noto Sans", "Noto Color Emoji", sans-serif;
    }
    .stApp { background: var(--background-color); color: var(--text-color); }
    [data-testid="stSidebar"] {
        background: var(--secondary-background-color);
        color: var(--text-color);
    }
    [data-testid="stSidebar"] * { color: inherit; }
    .hero { padding: 1.5rem 1.8rem; border-radius: 18px; color: #f7fbff;
            background: linear-gradient(115deg, #10213c, #1a4963 68%, #278b83); }
    .hero h1 { margin: 0; font-size: 2.2rem; }
    .hero p { margin: .5rem 0 0; color: #d4e5f2; }
    div[data-testid="stMetric"] {
        background: var(--secondary-background-color);
        color: var(--text-color);
        padding: 1rem;
        border: 1px solid var(--border-color);
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero"><h1>ROUTEOPT · Centro de operaciones</h1>'
    '<p>Simulación observable de percepción, planificación, replanificación y aprendizaje.</p></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Configuración de la jornada")
    n_orders = st.slider("Pedidos por jornada", min_value=10, max_value=60, value=20, step=2)
    n_couriers = st.slider("Repartidores", min_value=2, max_value=8, value=4)
    days = st.slider("Jornadas de aprendizaje", min_value=1, max_value=5, value=3)
    seed = st.number_input("Semilla reproducible", min_value=0, max_value=999999, value=2026)
    compare = st.checkbox("Comparar con planificación manual zonal", value=True)
    extra_variants = st.checkbox("Incluir EDD y ablaciones", value=False)
    run_simulation = st.button("▶ Ejecutar simulación", type="primary", use_container_width=True)

st.caption(
    "Cada variante recibe el mismo escenario (semilla y jornada). ROUTEOPT conserva su memoria "
    "entre jornadas; las variantes manuales no aprenden ni replanifican."
)

if run_simulation:
    cfg = Config(n_orders=n_orders, n_couriers=n_couriers)
    variants = {"routeopt": RouteOptAgent(cfg, seed=int(seed))}
    if compare:
        variants["manual_zonal"] = ManualZonal(cfg)
    if extra_variants:
        variants["manual_edd"] = ManualEDD(cfg)
        variants["routeopt_sin_aprendizaje"] = RouteOptAgent(cfg, seed=int(seed), learning=False)
        variants["routeopt_sin_replanificacion"] = RouteOptAgent(
            cfg, seed=int(seed), replanning=False
        )

    rows = []
    routeopt_log = None
    progress = st.progress(0, text="Preparando escenarios reproducibles...")
    total = days * len(variants)
    completed = 0
    for day in range(1, days + 1):
        for name, agent in variants.items():
            memory_logger = MemoryLogger() if name == "routeopt" and day == days else None
            metrics = run_day(
                cfg,
                int(seed),
                day,
                agent,
                logger=memory_logger,
            )
            metrics["variant"] = name
            rows.append(metrics)
            if memory_logger is not None:
                routeopt_log = memory_logger.records
            completed += 1
            progress.progress(
                completed / total,
                text=f"Jornada {day}/{days} · {name.replace('_', ' ')}",
            )
    progress.empty()

    final_scenario = Scenario(cfg, int(seed), days)
    st.session_state["routeopt_demo"] = {
        "metrics": rows,
        "records": routeopt_log or [],
        "orders": [
            {"id": order.id, "x": order.x, "y": order.y, "zone": order.zone,
             "w_start": order.w_start, "w_end": order.w_end}
            for order in final_scenario.orders
        ],
        "config": {
            "n_orders": n_orders,
            "n_couriers": n_couriers,
            "days": days,
            "seed": int(seed),
            "city_km": cfg.city_km,
        },
    }

result = st.session_state.get("routeopt_demo")
if result is None:
    st.info("Configura la simulación en el panel lateral y ejecútala para ver al agente en acción.")
    st.markdown(
        """
        **Ciclo del agente**

        1. **Percibe:** recibe pedidos pendientes, posición de la flota, tráfico sensado y eventos.
        2. **Decide:** evalúa ventanas horarias, distancia, carga y riesgo; planifica o conserva el plan.
        3. **Actúa:** asigna secuencias de entrega y notifica cambios a los repartidores.
        4. **Aprende:** actualiza el perfil de tráfico y el tiempo de servicio para las jornadas siguientes.
        """
    )
    st.stop()

metrics_df = pd.DataFrame(result["metrics"])
latest_metrics = metrics_df[metrics_df["day"] == result["config"]["days"]]
route_metrics = latest_metrics[latest_metrics["variant"] == "routeopt"].iloc[0]
baseline_rows = latest_metrics[latest_metrics["variant"] == "manual_zonal"]

st.subheader(f"Jornada {result['config']['days']} · resumen de operación")
cards = st.columns(4)
cards[0].metric("Distancia ROUTEOPT", f"{route_metrics['total_km']:.1f} km")
cards[1].metric("Entregas a tiempo", f"{route_metrics['on_time_pct']:.1f}%")
cards[2].metric("Demora media", f"{route_metrics['avg_delay_min']:.1f} min")
cards[3].metric("Replanificaciones", f"{int(route_metrics['replans'])}")

if not baseline_rows.empty:
    baseline = baseline_rows.iloc[0]
    saved_pct = 100 * (1 - route_metrics["total_km"] / baseline["total_km"])
    st.caption(
        f"Frente a la planificación manual zonal: "
        f"{saved_pct:+.1f}% de distancia ({baseline['total_km']:.1f} km manuales). "
        "Un porcentaje positivo indica reducción."
    )

tab_ops, tab_learning, tab_trace = st.tabs(
    ["🗺️ Operación y rutas", "📈 Comparación y aprendizaje", "🔎 Decisiones y eventos"]
)

with tab_ops:
    st.markdown("#### Recorrido observado por repartidor")
    order_lookup = {order["id"]: order for order in result["orders"]}
    outcome_events = [
        event for event in result["records"]
        if event["kind"] == "outcome" and "order" in event
    ]
    route_points = []
    for courier in range(result["config"]["n_couriers"]):
        stops = sorted(
            (event for event in outcome_events if event["courier"] == courier),
            key=lambda event: event["arrival"],
        )
        if not stops:
            continue
        color = f"Repartidor {courier + 1}"
        route_points.append(
            {"repartidor": color, "orden": 0, "x": 6.0, "y": 6.0, "etiqueta": "Depósito"}
        )
        for index, event in enumerate(stops, start=1):
            order = order_lookup[event["order"]]
            route_points.append(
                {"repartidor": color, "orden": index, "x": order["x"], "y": order["y"],
                 "etiqueta": f"Pedido {event['order']}", "hora": f"{event['arrival']:.0f} min"}
            )
        route_points.append(
            {"repartidor": color, "orden": len(stops) + 1, "x": 6.0, "y": 6.0,
             "etiqueta": "Regreso"}
        )

    if route_points:
        route_df = pd.DataFrame(route_points)
        base_chart = alt.Chart(route_df).encode(
            x=alt.X("x:Q", title="Este-oeste (km)", scale=alt.Scale(domain=[0, 12])),
            y=alt.Y("y:Q", title="Norte-sur (km)", scale=alt.Scale(domain=[0, 12])),
            color=alt.Color("repartidor:N", title="Flota"),
            detail="repartidor:N",
            order=alt.Order("orden:Q"),
            tooltip=["repartidor:N", "etiqueta:N", "hora:N", "x:Q", "y:Q"],
        )
        route_chart = (
            base_chart.mark_line(strokeWidth=2)
            + base_chart.mark_circle(size=75)
            + base_chart.mark_text(dy=-11, fontSize=9).encode(text="etiqueta:N")
        ).properties(height=440)
        st.altair_chart(route_chart, width="stretch")
        st.caption("La secuencia se reconstruye a partir de las entregas simuladas; el depósito está en el centro.")
    else:
        st.warning("No se encontraron entregas para dibujar la ruta.")

    delivery_rows = []
    for event in sorted(outcome_events, key=lambda item: item["arrival"]):
        delivery_rows.append(
            {
                "Pedido": event["order"],
                "Repartidor": event["courier"] + 1,
                "Llegada (min)": round(event["arrival"], 1),
                "Ventana": f"{event['w_start']:.0f}–{event['w_end']:.0f}",
                "A tiempo": "Sí" if not event["late"] else "No",
                "Distancia (km)": round(event["dist_km"], 2),
            }
        )
    st.dataframe(pd.DataFrame(delivery_rows), width="stretch", hide_index=True)

with tab_learning:
    st.markdown("#### Rendimiento por jornada")
    st.line_chart(metrics_df, x="day", y="total_km", color="variant", height=320)
    comparison = (
        metrics_df.groupby("variant", as_index=False)
        .agg(
            distancia_total_km=("total_km", "sum"),
            entregas_a_tiempo_pct=("on_time_pct", "mean"),
            demora_media_min=("avg_delay_min", "mean"),
            replans_promedio=("replans", "mean"),
        )
    )
    if "manual_zonal" in comparison["variant"].values:
        baseline_km = comparison.loc[
            comparison["variant"] == "manual_zonal", "distancia_total_km"
        ].iloc[0]
        comparison["reduccion_km_vs_manual_pct"] = comparison["distancia_total_km"].apply(
            lambda value: 100 * (1 - value / baseline_km)
        )
    st.dataframe(comparison.round(2), width="stretch", hide_index=True)

    traffic_rows = []
    for event in result["records"]:
        if event["kind"] != "percept":
            continue
        for zone, factor in event["traffic"].items():
            traffic_rows.append(
                {
                    "hora": event["sim_min"],
                    "zona": f"Zona {int(zone) + 1}",
                    "factor": factor,
                }
            )
    if traffic_rows:
        st.markdown("#### Tráfico percibido por los sensores")
        st.line_chart(
            pd.DataFrame(traffic_rows), x="hora", y="factor", color="zona",
            height=300, width="stretch",
        )
    st.caption(
        f"Jornadas aprendidas por ROUTEOPT: {int(route_metrics['day'])}. "
        "La memoria de tráfico y servicio se mantiene al avanzar entre jornadas de esta ejecución."
    )

with tab_trace:
    decision_events = [event for event in result["records"] if event["kind"] == "decision"]
    action_events = [event for event in result["records"] if event["kind"] == "action"]
    left, right = st.columns(2)
    with left:
        st.markdown("#### Decisiones del agente")
        decision_rows = [
            {
                "Hora simulada (min)": event["sim_min"],
                "Motivo": event.get("reason", ""),
                "Aceptada": "Sí" if event.get("accepted") else "No",
                "Utilidad antes": event.get("u_before"),
                "Utilidad después": event.get("u_after"),
                "Rutas modificadas": event.get("changed", 0),
            }
            for event in decision_events
        ]
        st.dataframe(pd.DataFrame(decision_rows), width="stretch", hide_index=True)
    with right:
        st.markdown("#### Acciones enviadas")
        action_rows = [
            {
                "Hora simulada (min)": event["sim_min"],
                "Tipo": event.get("type"),
                "Repartidor": event.get("courier", -1) + 1,
                "Pedidos": ", ".join(map(str, event.get("orders", []))),
                "Notificación": event.get("text", ""),
            }
            for event in action_events
        ]
        st.dataframe(pd.DataFrame(action_rows), width="stretch", hide_index=True)

    log_jsonl = "\n".join(json.dumps(event, ensure_ascii=False) for event in result["records"])
    st.download_button(
        "Descargar registro de la jornada (.jsonl)",
        data=log_jsonl,
        file_name="routeopt_jornada.jsonl",
        mime="application/x-ndjson",
    )
