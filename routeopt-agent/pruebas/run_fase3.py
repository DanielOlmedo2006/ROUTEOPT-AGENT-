"""Fase 3: pruebas contra las medidas de desempeño (umbrales en pruebas/umbrales.json, fijados de antemano).

Uso:  python -m pruebas.run_fase3            # 12 escenarios x 5 repeticiones x 10 jornadas
Salida (pruebas/resultados/): resultados_por_repeticion.csv, resumen_por_escenario.csv,
                              resumen_por_medida.json, tablas.md ; logs en pruebas/logs/
"""
from __future__ import annotations

import csv
import dataclasses
import json
import math
import os
import statistics as st
import time

from routeopt.agent import RouteOptAgent
from routeopt.baselines import ManualZonal
from routeopt.config import Config
from routeopt.env import Scenario
from routeopt.runner import run_day

HERE = os.path.dirname(os.path.abspath(__file__))
U = json.load(open(os.path.join(HERE, "umbrales.json"), encoding="utf-8"))
INVALID_IDS = {0, 1, 2}


class SinSensor(Scenario):
    """Falla esperada: la API de tráfico no entrega ningún dato."""
    def sensor(self, t):
        return {}


class EntradasInvalidas(Scenario):
    """Falla esperada: 3 pedidos con datos inválidos (ventana invertida, fuera de la ciudad, coordenada faltante)."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        o = self.orders
        o[0] = dataclasses.replace(o[0], w_end=o[0].w_start - 30.0)
        o[1] = dataclasses.replace(o[1], x=50.0, y=50.0)
        o[2] = dataclasses.replace(o[2], x=float("nan"))


ESCENARIOS = [
    ("N1_base", "normal", {}, Scenario),
    ("N2_ventanas_estrechas", "normal", dict(window_widths=(30.0, 45.0, 60.0)), Scenario),
    ("N3_volumen_alto", "normal", dict(n_orders=60), Scenario),
    ("N4_volumen_bajo", "normal", dict(n_orders=16), Scenario),
    ("N5_flota_reducida", "normal", dict(n_couriers=2), Scenario),
    ("L1_un_repartidor", "limite", dict(n_couriers=1, n_orders=20), Scenario),
    ("L2_un_pedido", "limite", dict(n_orders=1), Scenario),
    ("L3_ventanas_extremas", "limite", dict(window_widths=(15.0, 20.0, 30.0)), Scenario),
    ("A1_congestion_total", "adverso", dict(event_prob_zone=1.0), Scenario),
    ("A2_incidentes_totales", "adverso", dict(incident_prob=1.0), Scenario),
    ("F1_sensor_sin_dato", "falla_esperada", {}, SinSensor),
    ("F2_entradas_invalidas", "falla_esperada", {}, EntradasInvalidas),
]


def run_block(name, kw, cls, rep, seed, log_dir):
    cfg = Config(**kw)
    agent, base = RouteOptAgent(cfg, seed=seed), ManualZonal(cfg)
    A, fails, km_a, km_b = [], 0, 0.0, 0.0
    errors = set()
    for day in range(1, U["jornadas_por_repeticion"] + 1):
        lp = os.path.join(log_dir, f"{name}_rep1_dia01.jsonl") if (rep == 1 and day == 1) else None
        try:
            ma = run_day(cfg, seed, day, agent, lp, scenario_cls=cls)
        except Exception as e:                      # falla registrada, no oculta
            fails += 1
            errors.add(type(e).__name__)
            agent._day_open = False
            continue
        A.append(ma)
        try:
            mb = run_day(cfg, seed, day, base, None, scenario_cls=cls)
            km_a += ma["total_km"]
            km_b += mb["total_km"]
        except Exception:
            base.end_day()
    r = dict(escenario=name, repeticion=rep, semilla=seed, jornadas_ok=len(A), jornadas_fallidas=fails,
             errores="|".join(sorted(errors)))
    if A:
        r["M1"] = 100 * (1 - km_a / km_b) if km_b > 0 else None
        r["M2"] = st.mean(m["on_time_pct"] for m in A)
        r["M3"] = st.mean(m["avg_delay_min"] for m in A)
        r["M4"] = st.mean(m["replans"] for m in A)
        r["M5"] = st.mean(m["stops_max"] / (cfg.n_orders / cfg.n_couriers) for m in A)
    r["M6"] = 100.0 * len(A) / (len(A) + fails)
    if name.startswith("F2"):
        r["M7"] = 100.0 * len(INVALID_IDS & set(getattr(agent, "rejected_orders", []))) / len(INVALID_IDS)
    return r


def ok(op, v, thr):
    return v >= thr if op == ">=" else v <= thr


def main():
    out = os.path.join(HERE, "resultados")
    log_dir = os.path.join(HERE, "logs")
    os.makedirs(out, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    rows, t0 = [], time.time()
    cache = os.path.join(out, "parcial")
    os.makedirs(cache, exist_ok=True)
    for name, cat, kw, cls in ESCENARIOS:
        cf = os.path.join(cache, name + ".json")
        if os.path.exists(cf):                      # permite reanudar si la ejecución se interrumpe
            rows.extend(json.load(open(cf, encoding="utf-8")))
            continue
        block = [run_block(name, kw, cls, rep, U["semillas_base"] + rep, log_dir)
                 for rep in range(1, U["repeticiones"] + 1)]
        json.dump(block, open(cf, "w", encoding="utf-8"))
        rows.extend(block)
        print(f"{name:26s} listo ({time.time() - t0:.0f}s)", flush=True)
    keys = ["escenario", "repeticion", "semilla", "jornadas_ok", "jornadas_fallidas", "errores",
            "M1", "M2", "M3", "M4", "M5", "M6", "M7"]
    with open(os.path.join(out, "resultados_por_repeticion.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(r[k], 3) if isinstance(r.get(k), float) else r.get(k, "")) for k in keys})

    detail, per_measure = [], {}
    for m, spec in U["medidas"].items():
        per_measure[m] = dict(nombre=spec["nombre"], operador=spec["operador"], umbral=spec["umbral"],
                              escenarios=[], medias=[], todas=[], cumple_n=0)
        for name in spec["aplica"]:
            vals = [r[m] for r in rows if r["escenario"] == name and r.get(m) is not None]
            if not vals:
                continue
            mean = st.mean(vals)
            sd = st.stdev(vals) if len(vals) > 1 else 0.0
            n_ok = sum(ok(spec["operador"], v, spec["umbral"]) for v in vals)
            if m in ("M6", "M7"):
                cumple = n_ok == len(vals)
            else:
                cumple = ok(spec["operador"], mean, spec["umbral"]) and n_ok >= 4
            detail.append(dict(medida=m, escenario=name, media=round(mean, 2), sd=round(sd, 2),
                               minimo=round(min(vals), 2), maximo=round(max(vals), 2),
                               reps_ok=f"{n_ok}/{len(vals)}", cumple=cumple))
            pm = per_measure[m]
            pm["escenarios"].append(name)
            pm["medias"].append(mean)
            pm["todas"].extend(vals)
            pm["cumple_n"] += int(cumple)
    with open(os.path.join(out, "resumen_por_escenario.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(detail[0]))
        w.writeheader()
        w.writerows(detail)

    summary = {}
    for m, pm in per_measure.items():
        n = len(pm["escenarios"])
        summary[m] = dict(nombre=pm["nombre"], umbral=f'{pm["operador"]} {pm["umbral"]}', escenarios=n,
                          media_global=round(st.mean(pm["todas"]), 2),
                          sd_global=round(st.stdev(pm["todas"]), 2) if len(pm["todas"]) > 1 else 0.0,
                          rango_medias=[round(min(pm["medias"]), 2), round(max(pm["medias"]), 2)],
                          cumple=f'{pm["cumple_n"]}/{n}', repeticiones=len(pm["todas"]))
    json.dump(summary, open(os.path.join(out, "resumen_por_medida.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    md = ["| Medida | Escenario | Media ± sd | Mín–máx | Reps ok | ¿Cumple? |", "|---|---|---|---|---|---|"]
    for d in detail:
        md.append(f"| {d['medida']} | {d['escenario']} | {d['media']} ± {d['sd']} | {d['minimo']}–{d['maximo']} | "
                  f"{d['reps_ok']} | {'Sí' if d['cumple'] else 'No'} |")
    open(os.path.join(out, "tablas.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print("\n".join(md))


if __name__ == "__main__":
    main()
