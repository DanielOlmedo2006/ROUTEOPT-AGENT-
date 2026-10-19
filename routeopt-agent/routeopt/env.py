"""Simulador del entorno de ROUTEOPT-AGENT.

Propiedades de ambiente declaradas en el diseño (sección 3) y cómo las respeta el simulador:
  - Parcialmente observable: el agente NO ve el tráfico real; solo un sensor ruidoso (Percept.traffic),
    ni los tiempos de atención reales hasta que la entrega termina.
  - Estocástico: ruido en tiempos de viaje y atención, congestiones repentinas e incidentes de repartidores.
  - Secuencial: el orden de paradas determina la hora de llegada a las siguientes.
  - Dinámico: el tráfico cambia con el reloj, independiente de las acciones del agente.
  - Continuo: posiciones, distancias y tiempos son reales (float); el reloj avanza en ticks de 5 min.
  - Multirepartidor: una flota de N repartidores coordinada por un único agente de software.

El escenario es función pura de (seed, day): dos agentes distintos enfrentan EXACTAMENTE la misma
jornada (números aleatorios comunes), lo que permite comparaciones pareadas justas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .config import Config

DEPOT = -1  # id del nodo depósito


def zone_of(cfg: Config, x: float, y: float) -> int:
    k = cfg.zones_per_side
    cell = cfg.city_km / k
    i = min(k - 1, max(0, int(x // cell)))
    j = min(k - 1, max(0, int(y // cell)))
    return j * k + i


def road_km(cfg: Config, a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1]) * cfg.road_factor


# ---------------------------------------------------------------- datos de percepción / acción
@dataclass(frozen=True)
class Order:
    id: int
    x: float
    y: float
    w_start: float
    w_end: float
    zone: int


@dataclass
class CourierView:
    id: int
    pos: tuple          # posición GPS (ruidosa)
    available: bool
    route: list         # paradas aún no comprometidas (cola que ve la app del repartidor)
    committed: int | None   # pedido en curso (no se puede reasignar)
    free_node: int      # nodo donde quedará libre (DEPOT u id de pedido)
    free_t: float       # hora estimada en que quedará libre (ETA ruidoso)


@dataclass
class Percept:
    t: float
    orders: dict        # id -> Order (lista de entregas del sistema de pedidos)
    couriers: list      # list[CourierView]
    events: list        # entregas terminadas desde la percepción anterior
    traffic: dict       # zona -> factor de tráfico observado (ruidoso)
    unassigned: list    # pedidos sin repartidor asignado


@dataclass(frozen=True)
class AssignRoute:
    courier_id: int
    order_ids: tuple


@dataclass(frozen=True)
class Notify:
    courier_id: int
    text: str


# ---------------------------------------------------------------- escenario (una jornada)
class Scenario:
    def __init__(self, cfg: Config, seed: int, day: int):
        self.cfg, self.seed, self.day = cfg, seed, day
        nz = cfg.zones_per_side ** 2
        # Propiedades de la ciudad: iguales todos los días (lo que el agente puede aprender)
        fixed = np.random.default_rng([seed, 777])
        self.zone_bias = fixed.uniform(0.0, 0.10, nz)
        self.zone_bias[nz // 2] += 0.20                      # el centro es más congestionado
        self.zone_service_mean = fixed.uniform(3.0, 7.0, nz)  # minutos de atención por zona

        rng = np.random.default_rng([seed, day, 1])
        centers = rng.uniform(1.5, cfg.city_km - 1.5, size=(3, 2))
        orders = []
        for i in range(cfg.n_orders):
            if rng.random() < 0.7:
                c = centers[int(rng.integers(3))]
                x, y = np.clip(rng.normal(c, 1.5), 0.0, cfg.city_km - 1e-6)
            else:
                x, y = rng.uniform(0.0, cfg.city_km - 1e-6, 2)
            ws = cfg.day_start + 30.0 * int(rng.integers(0, 19))
            we = ws + float(rng.choice(list(cfg.window_widths)))
            orders.append(Order(i, float(x), float(y), ws, we, zone_of(cfg, x, y)))
        self.orders = orders
        s = cfg.service_sigma
        self.service_true = {
            o.id: float(self.zone_service_mean[o.zone] * math.exp(rng.normal(0, s) - s * s / 2))
            for o in orders
        }
        # Tráfico: ruido AR(1) por zona + congestiones repentinas
        self.K = int(16 * 60 / cfg.tick_min)
        self.noise = np.zeros((nz, self.K))
        for k in range(1, self.K):
            self.noise[:, k] = 0.95 * self.noise[:, k - 1] + rng.normal(0, 0.03, nz)
        self.events = [[] for _ in range(nz)]
        for z in range(nz):
            if rng.random() < cfg.event_prob_zone:
                t0 = cfg.day_start + float(rng.uniform(60, 600))
                self.events[z].append((t0, t0 + float(rng.uniform(30, 60)), float(rng.uniform(0.5, 1.0))))
        # Incidentes de repartidores
        self.incidents = []
        for _ in range(cfg.n_couriers):
            if rng.random() < cfg.incident_prob:
                self.incidents.append((cfg.day_start + float(rng.uniform(120, 540)),
                                       float(rng.uniform(*cfg.incident_dur))))
            else:
                self.incidents.append(None)

    # -- tráfico verdadero (oculto al agente)
    @staticmethod
    def profile(t: float) -> float:
        h = t / 60.0
        return 1.0 + 0.45 * math.exp(-((h - 8.5) / 1.0) ** 2) + 0.50 * math.exp(-((h - 18.0) / 1.2) ** 2)

    def factor(self, z: int, t: float) -> float:
        k = min(self.K - 1, max(0, int((t - self.cfg.day_start) // self.cfg.tick_min)))
        f = self.profile(t) * (1.0 + self.zone_bias[z]) + self.noise[z, k]
        for (t0, t1, extra) in self.events[z]:
            if t0 <= t < t1:
                f += extra
        return max(0.7, float(f))

    def sensor(self, t: float) -> dict:
        """API de tráfico: factor observado por zona, con ruido."""
        k = int((t - self.cfg.day_start) // self.cfg.tick_min)
        rng = np.random.default_rng([self.seed, self.day, 3, max(k, 0)])
        nz = self.cfg.zones_per_side ** 2
        eps = rng.normal(0, self.cfg.sensor_sigma, nz)
        return {z: float(self.factor(z, t) * (1 + eps[z])) for z in range(nz)}

    def leg_noise(self, a: int, b: int) -> float:
        s = self.cfg.leg_sigma
        rng = np.random.default_rng([self.seed, self.day, 2, a + 1, b + 1])
        return math.exp(rng.normal(0, s) - s * s / 2)


# ---------------------------------------------------------------- entorno
class _Courier:
    def __init__(self, cid, depot, inc):
        self.id = cid
        self.node = DEPOT
        self.pos = depot
        self.route = []
        self.t_free = 0.0
        self.stop_end = -1.0
        self.seg = None
        self.cur_order = None
        self.inc = inc
        self.inc_done = False
        self.down_until = -1.0
        self.km = self.travel = self.service = self.wait = 0.0


class Env:
    def __init__(self, sc: Scenario):
        self.sc, self.cfg = sc, sc.cfg
        self.orders = {o.id: o for o in sc.orders}
        self.couriers = [_Courier(i, self.cfg.depot, sc.incidents[i]) for i in range(self.cfg.n_couriers)]
        for c in self.couriers:
            c.t_free = self.cfg.day_start
        self.outcomes = {}
        self._unreported = []

    # ---- percepción
    def _position(self, c, t):
        if c.seg:
            ts, arr, p0, p1 = c.seg
            if t < arr and arr > ts:
                f = max(0.0, (t - ts) / (arr - ts))
                return (p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)
        return c.pos

    def observe(self, t: float) -> Percept:
        cfg = self.cfg
        k = int((t - cfg.day_start) // cfg.tick_min)
        views = []
        for c in self.couriers:
            rng = np.random.default_rng([self.sc.seed, self.sc.day, 4, max(k, 0), c.id])
            px, py = self._position(c, t)
            gx, gy = rng.normal(0, cfg.gps_sigma_km, 2)
            eta = rng.normal(0, cfg.eta_sigma_min)
            available = not (c.inc_done and t < c.down_until)
            committed = c.cur_order if c.stop_end > t else None
            views.append(CourierView(c.id, (px + float(gx), py + float(gy)), available, list(c.route),
                                     committed, c.node, max(c.t_free, t) + float(eta)))
        events = [e for e in self._unreported if e["finish"] <= t]
        self._unreported = [e for e in self._unreported if e["finish"] > t]
        assigned = {o for c in self.couriers for o in c.route}
        unassigned = [o for o in self.orders if o not in self.outcomes and o not in assigned]
        return Percept(t, dict(self.orders), views, events, self.sc.sensor(t), unassigned)

    # ---- actuadores
    def apply(self, actions, t: float):
        routes = {}
        for a in actions:
            if isinstance(a, AssignRoute):
                routes[a.courier_id] = list(a.order_ids)
        flat = [o for r in routes.values() for o in r]
        if len(flat) != len(set(flat)):
            raise ValueError("pedido asignado dos veces")
        other = {o for c in self.couriers if c.id not in routes for o in c.route}
        if set(flat) & other:
            raise ValueError("pedido ya asignado a otro repartidor")
        if any(o in self.outcomes for o in flat):
            raise ValueError("pedido ya comprometido/entregado")
        for cid, r in routes.items():
            c = self.couriers[cid]
            c.route = r
            if r:
                c.t_free = max(c.t_free, t)

    # ---- dinámica del mundo
    def advance(self, t_end: float):
        sc, cfg = self.sc, self.cfg
        for c in self.couriers:
            while c.route and c.t_free <= t_end:
                ts = c.t_free
                if c.inc and not c.inc_done and ts >= c.inc[0]:
                    c.inc_done = True
                    c.down_until = ts + c.inc[1]
                    c.t_free = c.down_until
                    continue
                oid = c.route.pop(0)
                o = self.orders[oid]
                p0, p1 = c.pos, (o.x, o.y)
                d = road_km(cfg, p0, p1)
                f = 0.5 * (sc.factor(zone_of(cfg, *p0), ts) + sc.factor(o.zone, ts))
                tt = d / cfg.base_speed_kmh * 60.0 * f * sc.leg_noise(c.node, oid)
                arr = ts + tt
                start = max(arr, o.w_start)
                svc = sc.service_true[oid]
                fin = start + svc
                c.km += d
                c.travel += tt
                c.wait += start - arr
                c.service += svc
                c.seg, c.pos, c.node, c.cur_order = (ts, arr, p0, p1), p1, oid, oid
                c.t_free = c.stop_end = fin
                ev = dict(order=oid, courier=c.id, zone=o.zone, arrival=arr, start=start, finish=fin,
                          late=bool(arr > o.w_end + 1e-9), dist_km=d, travel_min=tt, service_min=svc,
                          w_start=o.w_start, w_end=o.w_end)
                self.outcomes[oid] = ev
                self._unreported.append(ev)

    def all_delivered(self, t: float) -> bool:
        return len(self.outcomes) == len(self.orders) and all(e["finish"] <= t for e in self.outcomes.values())

    # ---- medidas de desempeño (sección 7)
    def summary(self) -> dict:
        cfg = self.cfg
        outs = list(self.outcomes.values())
        km = sum(c.km + road_km(cfg, c.pos, cfg.depot) for c in self.couriers)  # incluye regreso al depósito
        makespan = max(e["finish"] for e in outs) - cfg.day_start
        busy = [(c.travel + c.service) / makespan for c in self.couriers]
        stops = [sum(1 for e in outs if e['courier'] == c.id) for c in self.couriers]
        return dict(
            total_km=km,
            on_time_pct=100.0 * sum(not e["late"] for e in outs) / len(outs),
            avg_delay_min=sum(e["start"] - e["w_start"] for e in outs) / len(outs),
            avg_late_min=sum(max(0.0, e["arrival"] - e["w_end"]) for e in outs) / len(outs),
            utilization_pct=100.0 * sum(busy) / len(busy),
            makespan_min=makespan,
            stops_max=max(stops),
            stops_min=min(stops),
            n_orders=len(outs),
        )
