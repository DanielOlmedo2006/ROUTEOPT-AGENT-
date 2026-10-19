"""Pruebas automáticas: propiedades del entorno (sección 3) y coherencia del agente (sección 2)."""
import dataclasses

from routeopt.agent import RouteOptAgent
from routeopt.baselines import ManualZonal
from routeopt.config import Config
from routeopt.env import Env, Scenario
from routeopt.runner import run_day

CFG = Config(n_orders=20)


def test_reproducible_con_misma_semilla():
    a = run_day(CFG, 7, 1, RouteOptAgent(CFG, seed=1))
    b = run_day(CFG, 7, 1, RouteOptAgent(CFG, seed=1))
    assert a["total_km"] == b["total_km"] and a["on_time_pct"] == b["on_time_pct"]


def test_entorno_estocastico_semillas_distintas_dan_jornadas_distintas():
    a = run_day(CFG, 1, 1, ManualZonal(CFG))
    b = run_day(CFG, 2, 1, ManualZonal(CFG))
    assert a["total_km"] != b["total_km"]


def test_todos_los_pedidos_se_atienden_una_sola_vez():
    m = run_day(CFG, 3, 1, RouteOptAgent(CFG, seed=0))
    assert m["n_orders"] == CFG.n_orders


def test_percepcion_parcialmente_observable_no_expone_trafico_real():
    sc = Scenario(CFG, 3, 1)
    env = Env(sc)
    t = CFG.day_start + 60
    p = env.observe(t)
    fields = {f.name for f in dataclasses.fields(p)}
    assert "true_traffic" not in fields
    # el sensor es ruidoso: no coincide con el factor verdadero
    assert any(abs(p.traffic[z] - sc.factor(z, t)) > 1e-9 for z in p.traffic)


def test_utilidad_del_plan_mejora_la_secuencia_inicial():
    """El agente compara alternativas: su plan debe tener utilidad >= que el plan manual en su propio modelo."""
    sc = Scenario(CFG, 5, 1)
    env = Env(sc)
    p = env.observe(CFG.day_start)
    ag = RouteOptAgent(CFG, seed=0)
    ag._perceive(p)
    ag._memo = {}
    manual = ManualZonal(CFG)._routes(p)
    u_manual, _ = ag._utility({i: r for i, r in enumerate(manual)})
    routes, u_agent = ag._plan({c.id: [] for c in p.couriers}, list(p.unassigned), 2)
    assert u_agent >= u_manual


def test_replanifica_cuando_un_repartidor_falla():
    cfg = Config(n_orders=24, incident_prob=1.0)   # todos los repartidores sufren incidente
    ag = RouteOptAgent(cfg, seed=0)
    m = run_day(cfg, 11, 1, ag)
    assert m["n_orders"] == 24 and m["replans"] >= 1


def test_aprendizaje_actualiza_perfil_de_trafico():
    ag = RouteOptAgent(CFG, seed=0)
    antes = [row[:] for row in ag.profile]
    run_day(CFG, 4, 1, ag)
    assert ag.profile != antes and ag.days_seen == 1


def test_log_contiene_percepciones_decisiones_y_acciones(tmp_path):
    import json
    path = str(tmp_path / "log.jsonl")
    run_day(CFG, 4, 1, RouteOptAgent(CFG, seed=0), log_path=path)
    kinds = {json.loads(l)["kind"] for l in open(path, encoding="utf-8")}
    assert {"percept", "decision", "action", "outcome", "summary"} <= kinds
