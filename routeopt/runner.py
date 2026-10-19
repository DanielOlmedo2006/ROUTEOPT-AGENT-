"""Ejecuta jornadas simuladas y compara agentes sobre los mismos escenarios."""
from __future__ import annotations

import argparse
import csv
import json
import os
import time

from .agent import RouteOptAgent
from .baselines import ManualEDD, ManualZonal
from .config import Config
from .env import AssignRoute, Env, Notify, Scenario
from .logger import JsonlLogger, NullLogger


def run_day(cfg: Config, seed: int, day: int, agent, log_path: str | None = None) -> dict:
    """Una jornada completa: bucle percepción -> decisión -> acción, un ciclo por tick de 5 min simulados."""
    env = Env(Scenario(cfg, seed, day))
    logger = JsonlLogger(log_path) if log_path else NullLogger()
    if hasattr(agent, "logger"):
        agent.logger = logger
    t = cfg.day_start
    while True:
        p = env.observe(t)                                   # 1) PERCEPCIÓN (sensores)
        logger.log("percept", t, traffic={z: round(v, 3) for z, v in p.traffic.items()},
                   couriers=[dict(id=c.id, pos=[round(c.pos[0], 3), round(c.pos[1], 3)],
                                  available=c.available, queue=len(c.route), committed=c.committed)
                             for c in p.couriers],
                   unassigned=len(p.unassigned))
        for e in p.events:
            logger.log("outcome", t, **e)
        actions = agent.step(p)                              # 2) DECISIÓN (dentro de agent.step)
        for a in actions:                                    # 3) ACCIÓN (actuadores)
            if isinstance(a, AssignRoute):
                logger.log("action", t, type="AssignRoute", courier=a.courier_id, orders=list(a.order_ids))
            elif isinstance(a, Notify):
                logger.log("action", t, type="Notify", courier=a.courier_id, text=a.text)
        env.apply(actions, t)
        t += cfg.tick_min
        env.advance(t)
        if env.all_delivered(t):
            p = env.observe(t)                               # percepción final (cierra el aprendizaje)
            for e in p.events:
                logger.log("outcome", t, **e)
            agent.step(p)
            break
        if t > cfg.day_start + 30 * 60:
            raise RuntimeError("la jornada no termina: hay pedidos sin asignar")
    agent.end_day()
    m = env.summary()
    m.update(day=day, replans=agent.replans)
    logger.log("summary", t, **m)
    logger.close()
    return m


def make_variants(cfg: Config, seed: int, ablations: bool):
    v = {
        "manual_zonal": ManualZonal(cfg),
        "manual_edd": ManualEDD(cfg),
        "routeopt": RouteOptAgent(cfg, seed=seed),
    }
    if ablations:
        v["routeopt_sin_aprendizaje"] = RouteOptAgent(cfg, seed=seed, learning=False)
        v["routeopt_sin_replanificacion"] = RouteOptAgent(cfg, seed=seed, replanning=False)
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(description="ROUTEOPT-AGENT: simulación y comparación contra planificación manual")
    ap.add_argument("--days", type=int, default=10, help="jornadas simuladas (10 = dos semanas hábiles)")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default="results")
    ap.add_argument("--ablations", action="store_true", help="incluye variantes sin aprendizaje / sin replanificación")
    ap.add_argument("--orders", type=int, default=None)
    ap.add_argument("--couriers", type=int, default=None)
    ap.add_argument("--windows", default=None, help="anchos de ventana en minutos separados por coma, p. ej. 30,45,60")
    a = ap.parse_args(argv)

    kw = {}
    if a.orders:
        kw["n_orders"] = a.orders
    if a.couriers:
        kw["n_couriers"] = a.couriers
    if a.windows:
        kw["window_widths"] = tuple(float(x) for x in a.windows.split(","))
    cfg = Config(**kw)
    variants = make_variants(cfg, a.seed, a.ablations)
    rows = []
    t0 = time.time()
    for day in range(1, a.days + 1):
        for name, agent in variants.items():
            m = run_day(cfg, a.seed, day, agent, os.path.join(a.out, "logs", f"{name}_dia{day:02d}.jsonl"))
            m["variant"] = name
            rows.append(m)
        print(f"jornada {day}/{a.days} lista ({time.time() - t0:.0f}s)", flush=True)
    variants["routeopt"].save_memory(os.path.join(a.out, "memoria_routeopt.json"))

    os.makedirs(a.out, exist_ok=True)
    keys = ["variant", "day", "total_km", "on_time_pct", "avg_delay_min", "avg_late_min",
            "utilization_pct", "makespan_min", "stops_max", "stops_min", "replans", "n_orders"]
    with open(os.path.join(a.out, "metricas_por_jornada.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(r[k], 3) if isinstance(r[k], float) else r[k]) for k in keys})

    summary = summarize(rows, "manual_zonal")
    with open(os.path.join(a.out, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print_summary(summary)


def summarize(rows, base_name):
    by = {}
    for r in rows:
        by.setdefault(r["variant"], {})[r["day"]] = r
    base = by[base_name]
    out = {}
    for name, days in by.items():
        ds = sorted(days)
        km = sum(days[d]["total_km"] for d in ds)
        km_b = sum(base[d]["total_km"] for d in ds)
        per_day = [100 * (1 - days[d]["total_km"] / base[d]["total_km"]) for d in ds]
        n = len(ds)
        out[name] = dict(
            total_km=km,
            reduccion_km_pct_vs_base=100 * (1 - km / km_b),
            reduccion_media_por_jornada_pct=sum(per_day) / n,
            reduccion_minima_jornada_pct=min(per_day),
            on_time_pct=sum(days[d]["on_time_pct"] for d in ds) / n,
            avg_delay_min=sum(days[d]["avg_delay_min"] for d in ds) / n,
            utilization_pct=sum(days[d]["utilization_pct"] for d in ds) / n,
            stops_max_prom=sum(days[d]["stops_max"] for d in ds) / n,
            stops_min_prom=sum(days[d]["stops_min"] for d in ds) / n,
            replans_por_jornada=sum(days[d]["replans"] for d in ds) / n,
        )
    return out


def print_summary(s):
    print(f"\n{'variante':30s}{'km':>8s}{'red.%':>7s}{'min%':>7s}{'a tiempo%':>10s}{'demora':>8s}"
          f"{'paradas max/min':>17s}{'replan':>8s}")
    for name, v in s.items():
        print(f"{name:30s}{v['total_km']:8.1f}{v['reduccion_km_pct_vs_base']:7.1f}"
              f"{v['reduccion_minima_jornada_pct']:7.1f}{v['on_time_pct']:10.1f}{v['avg_delay_min']:8.1f}"
              f"{v['stops_max_prom']:11.1f}/{v['stops_min_prom']:<4.1f}{v['replans_por_jornada']:8.1f}")
