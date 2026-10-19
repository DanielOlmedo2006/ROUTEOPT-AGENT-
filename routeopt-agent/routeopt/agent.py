"""ROUTEOPT-AGENT: agente basado en utilidad con aprendizaje (Russell & Norvig).

Ciclo del agente (función del agente), llamado por el runner en cada tick:

    step(percepto) = _perceive  ->  _decide  ->  _act
        percepción:  actualiza el MODELO interno (memoria de corto plazo del día) y aprende (largo plazo)
        decisión:    compara alternativas de asignación/secuencia con la FUNCIÓN DE UTILIDAD
        acción:      traduce la decisión en acciones sobre los actuadores (AssignRoute, Notify)

Qué hace este código y qué no:
  - TODO el razonamiento (utilidad, búsqueda local, replanificación, aprendizaje) es código propio en Python.
  - No usa LLM ni APIs de pago. Las "herramientas externas" del diseño (API de mapas/tráfico, app del
    repartidor, sistema de pedidos) están reemplazadas por el simulador (routeopt/env.py).
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field

from .config import Config
from .env import AssignRoute, Notify, Percept, road_km, zone_of
from .logger import NullLogger


@dataclass
class Decision:
    reason: str
    routes: dict | None = None          # None = mantener el plan actual
    u_before: float | None = None
    u_after: float | None = None
    accepted: bool = False
    initial: bool = False


class RouteOptAgent:
    name = "routeopt"

    def __init__(self, cfg: Config, seed: int = 0, learning: bool = True, replanning: bool = True,
                 logger=None):
        self.cfg, self.learning, self.replanning = cfg, learning, replanning
        self.logger = logger or NullLogger()
        self.rng = random.Random(seed)
        nz = cfg.zones_per_side ** 2
        # ---- MEMORIA DE LARGO PLAZO (persiste entre jornadas; es lo que el agente aprende)
        self.profile = [[1.0] * cfg.n_buckets for _ in range(nz)]   # factor de tráfico esperado por zona/franja
        self.service_mean = [4.0] * nz                              # minutos de atención esperados por zona
        self.service_n = [0] * nz
        self.days_seen = 0
        self._day_open = False
        self.replans = 0

    # ====================================================================== función del agente
    def step(self, p: Percept) -> list:
        self._perceive(p)
        decision = self._decide(p)
        return self._act(decision, p)

    # ====================================================================== PERCEPCIÓN
    def _bucket(self, t: float) -> int:
        b = int((t - self.cfg.day_start) // self.cfg.bucket_min)
        return min(self.cfg.n_buckets - 1, max(0, b))

    def _start_day(self, p: Percept):
        cfg = self.cfg
        n = len(p.orders)
        # Memoria de corto plazo del día: pedidos, matriz de distancias, estado de la jornada
        self.ws = {o.id: o.w_start for o in p.orders.values()}
        self.we = {o.id: o.w_end for o in p.orders.values()}
        pts = [cfg.depot] + [(p.orders[i].x, p.orders[i].y) for i in range(n)]
        self.Z = [zone_of(cfg, *q) for q in pts]            # zona del nodo (índice = id + 1)
        self.D = [[road_km(cfg, a, b) for b in pts] for a in pts]
        self._obs = {}
        self._planned = False
        self.last_replan = -1e9
        self.was_down = set()
        self.plan_nstrict = 0
        self.replans = 0
        self.dev = [1.0] * (cfg.zones_per_side ** 2)
        self._day_open = True

    def _perceive(self, p: Percept):
        if not self._day_open:
            self._start_day(p)
        cfg = self.cfg
        self.now = p.t
        self.cv = {c.id: c for c in p.couriers}
        b = self._bucket(p.t)
        for z, obs in p.traffic.items():
            self._obs.setdefault((z, b), []).append(obs)
            self.dev[z] = min(2.5, max(0.5, obs / self.profile[z][b]))   # desviación respecto a lo esperado
        if self.learning:
            for e in p.events:                                         # aprendizaje en línea: tiempo de atención
                z = e["zone"]
                self.service_n[z] += 1
                alpha = max(0.1, 1.0 / self.service_n[z])
                self.service_mean[z] += alpha * ((e["finish"] - e["start"]) - self.service_mean[z])

    # ====================================================================== MODELO DE TRANSICIÓN + UTILIDAD
    def _f(self, z: int, t: float) -> float:
        """Factor de tráfico estimado: perfil aprendido, corregido por el sensor actual (decae con el horizonte)."""
        prof = self.profile[z][self._bucket(t)]
        dt = max(0.0, t - self.now)
        return prof * (1.0 + (self.dev[z] - 1.0) * math.exp(-dt / self.cfg.tau_min))

    def _route_eval(self, start_node: int, start_t: float, seq):
        """Simula esperadamente una ruta. Devuelve (km, retraso_con_margen, n_con_margen, max_retraso, n_tarde, min_trabajo)."""
        cfg, D, Z = self.cfg, self.D, self.Z
        t, node = start_t, start_node
        km = late_b = max_over = busy = 0.0
        n_b = n_strict = 0
        for oid in seq:
            d = D[node + 1][oid + 1]
            km += d
            f = 0.5 * (self._f(Z[node + 1], t) + self._f(Z[oid + 1], t))
            tt = d / cfg.base_speed_kmh * 60.0 * f
            t += tt
            busy += tt + self.service_mean[Z[oid + 1]]
            we = self.we[oid]
            over_b = t - (we - cfg.late_buffer_min)
            if over_b > 0:
                late_b += over_b
                n_b += 1
            if t > we:
                n_strict += 1
                max_over = max(max_over, t - we)
            t = max(t, self.ws[oid]) + self.service_mean[Z[oid + 1]]
            node = oid
        km += D[node + 1][0]                      # regreso al depósito
        return km, late_b, n_b, max_over, n_strict, busy

    def _cost(self, cid: int, seq) -> float:
        key = (cid, tuple(seq))
        v = self._memo.get(key)
        if v is None:
            c = self.cv[cid]
            km, late_b, n_b, _, _, busy = self._route_eval(c.free_node, c.free_t, seq)
            cfg = self.cfg
            v = (cfg.w_dist * km + cfg.w_late_min * late_b + cfg.w_late_stop * n_b
                 + cfg.w_load * (busy / 60.0) ** 2)
            self._memo[key] = v
        return v

    def _utility(self, routes: dict):
        """U(plan) = -(w_dist*km + w_late_min*min_tarde + w_late_stop*n_tarde + w_load*horas^2), estimada con el modelo."""
        self._memo = getattr(self, "_memo", {})
        total, mx, ns = 0.0, 0.0, 0
        for cid, seq in routes.items():
            total += self._cost(cid, seq)
            c = self.cv[cid]
            _, _, _, m, n, _ = self._route_eval(c.free_node, c.free_t, seq)
            mx, ns = max(mx, m), ns + n
        return -total, {"max_late_min": mx, "n_late": ns}

    # ====================================================================== DECISIÓN
    def _decide(self, p: Percept) -> Decision:
        cfg = self.cfg
        self._memo = {}
        cur = {c.id: list(c.route) for c in p.couriers}
        unassigned = list(p.unassigned)

        if not self._planned:
            routes, u = self._plan(cur, unassigned, cfg.restarts_init)
            return Decision("plan_inicial", routes, None, u, True, True)
        if not self.replanning:
            return Decision("replanificacion_desactivada")

        u_cur, st = self._utility(cur)
        down = {c.id for c in p.couriers if not c.available}
        back = self.was_down - down
        self.was_down = down
        mandatory = []
        if any(cur[c] for c in down):
            mandatory.append("incidente_repartidor")
        if unassigned:
            mandatory.append("pedidos_sin_asignar")
        optional = []
        if back:
            optional.append("repartidor_disponible")
        if (self.now - self.last_replan >= cfg.min_replan_gap and
                (st["max_late_min"] > cfg.risk_max_late_min or st["n_late"] >= self.plan_nstrict + 2)):
            optional.append("riesgo_de_retraso")

        if not mandatory and not optional:
            return Decision("sin_cambios", None, u_cur, u_cur, False)

        routes, u_new = self._plan(cur, unassigned, 1 if mandatory else 0)
        accept = bool(mandatory) or u_new > u_cur + cfg.replan_eps
        reason = "+".join(mandatory + optional)
        return Decision(reason, routes if accept else None, u_cur, u_new, accept)

    # ---- planificación: inserción más barata + búsqueda local, comparando alternativas por utilidad
    def _plan(self, cur: dict, unassigned: list, restarts: int):
        active = [cid for cid, c in self.cv.items() if c.available]
        if not active:
            return cur, self._utility(cur)[0]
        pool = list(unassigned) + [o for cid, r in cur.items() if cid not in active for o in r]
        base = {cid: list(cur[cid]) for cid in active}
        best_R, best_u = None, -math.inf
        for r in range(restarts + 1):
            R = {cid: list(s) for cid, s in base.items()}
            order = sorted(pool, key=lambda o: (self.ws[o], self.we[o]))
            if r > 0:
                self.rng.shuffle(order)
            for o in order:
                self._insert_best(R, o)
            self._local_search(R)
            u = -sum(self._cost(cid, R[cid]) for cid in active)
            if u > best_u:
                best_R, best_u = R, u
        routes = {cid: (best_R[cid] if cid in best_R else []) for cid in self.cv}
        return routes, self._utility(routes)[0]

    def _insert_best(self, R: dict, o: int):
        best = None
        for cid, seq in R.items():
            base = self._cost(cid, seq)
            for pos in range(len(seq) + 1):
                d = self._cost(cid, seq[:pos] + [o] + seq[pos:]) - base
                if best is None or d < best[0]:
                    best = (d, cid, pos)
        R[best[1]].insert(best[2], o)

    def _local_search(self, R: dict):
        eps = 1e-6
        for _ in range(self.cfg.max_ls_passes):
            improved = False
            # 1) reubicar un pedido en la mejor posición de cualquier ruta
            for o in [o for s in R.values() for o in s]:
                owner = next(cid for cid, s in R.items() if o in s)
                seq = R[owner]
                wo = [x for x in seq if x != o]
                remove_gain = self._cost(owner, seq) - self._cost(owner, wo)
                best = None
                for cid, s in R.items():
                    s0 = wo if cid == owner else s
                    base = self._cost(cid, s0)
                    for pos in range(len(s0) + 1):
                        d = self._cost(cid, s0[:pos] + [o] + s0[pos:]) - base
                        if best is None or d < best[0]:
                            best = (d, cid, pos)
                if best[0] - remove_gain < -eps:
                    R[owner] = wo
                    R[best[1]].insert(best[2], o)
                    improved = True
            # 2) 2-opt dentro de cada ruta
            for cid in R:
                seq = R[cid]
                for i in range(len(seq) - 1):
                    for j in range(i + 1, len(seq)):
                        new = seq[:i] + seq[i:j + 1][::-1] + seq[j + 1:]
                        if self._cost(cid, new) < self._cost(cid, seq) - eps:
                            seq = new
                            improved = True
                R[cid] = seq
            # 3) intercambio de dos pedidos entre rutas
            ids = list(R)
            for ia in range(len(ids)):
                for ib in range(ia + 1, len(ids)):
                    a, b = ids[ia], ids[ib]
                    for i in range(len(R[a])):
                        for j in range(len(R[b])):
                            sa, sb = R[a], R[b]
                            na = sa[:i] + [sb[j]] + sa[i + 1:]
                            nb = sb[:j] + [sa[i]] + sb[j + 1:]
                            if self._cost(a, na) + self._cost(b, nb) < self._cost(a, sa) + self._cost(b, sb) - eps:
                                R[a], R[b] = na, nb
                                improved = True
            if not improved:
                break

    # ====================================================================== ACCIÓN
    def _act(self, d: Decision, p: Percept) -> list:
        extra = dict(reason=d.reason, accepted=d.accepted,
                     u_before=d.u_before, u_after=d.u_after)
        if d.routes is None:
            self.logger.log("decision", p.t, **extra, changed=0)
            return []
        actions, changed = [], 0
        for cid, new in d.routes.items():
            if d.initial or new != list(self.cv[cid].route):
                actions.append(AssignRoute(cid, tuple(new)))
                msg = (f"Ruta del día: {len(new)} paradas" if d.initial
                       else f"Ruta actualizada ({d.reason}): {len(new)} paradas pendientes")
                actions.append(Notify(cid, msg))
                changed += 1
        self.logger.log("decision", p.t, **extra, changed=changed,
                        routes={str(k): v for k, v in d.routes.items()})
        self._planned = True
        _, st = self._utility(d.routes)
        self.plan_nstrict = st["n_late"]
        if not d.initial:
            self.last_replan = self.now
            self.replans += 1
        return actions

    # ====================================================================== APRENDIZAJE (fin de jornada)
    def end_day(self):
        """Actualiza el perfil de tráfico con el promedio observado hoy (media móvil entre jornadas)."""
        if self.learning:
            alpha = max(0.2, 1.0 / (self.days_seen + 1))
            for (z, b), vals in self._obs.items():
                m = sum(vals) / len(vals)
                self.profile[z][b] += alpha * (m - self.profile[z][b])
        self.days_seen += 1
        self._day_open = False

    def save_memory(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(profile=self.profile, service_mean=self.service_mean,
                           service_n=self.service_n, days_seen=self.days_seen), f)

    def load_memory(self, path: str):
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        self.profile, self.service_mean = m["profile"], m["service_mean"]
        self.service_n, self.days_seen = m["service_n"], m["days_seen"]
