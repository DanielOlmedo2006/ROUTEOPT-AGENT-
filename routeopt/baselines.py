"""Líneas base de "planificación manual" contra las que se mide la reducción de distancia.

El diseño habla de una "planificación manual actual" sin definirla. Aquí se modela como un despachador
humano que arma las rutas UNA vez al inicio de la jornada y no las reajusta. Es un PROXY: si el equipo
dispone de rutas manuales reales, debe reemplazarlas por ellas y documentarlo.

  - ManualZonal (línea base principal): reparte los pedidos por sectores angulares alrededor del depósito
    (cada repartidor atiende un sector, con igual número de pedidos) y los visita por hora de apertura
    de ventana. Es lo que haría un despachador con criterio geográfico.
  - ManualEDD (línea base débil, solo para sensibilidad): reparto rotativo por hora de ventana, sin criterio geográfico.
"""
from __future__ import annotations

import math

from .env import AssignRoute, Percept


class _OneShot:
    replans = 0

    def __init__(self, cfg):
        self.cfg = cfg
        self._done = False

    def step(self, p: Percept) -> list:
        if self._done:
            return []
        self._done = True
        return [AssignRoute(i, tuple(r)) for i, r in enumerate(self._routes(p))]

    def end_day(self):
        self._done = False

    def _routes(self, p: Percept):
        raise NotImplementedError


class ManualZonal(_OneShot):
    name = "manual_zonal"

    def _routes(self, p: Percept):
        k = self.cfg.n_couriers
        dx, dy = self.cfg.depot
        ids = sorted(p.orders, key=lambda i: math.atan2(p.orders[i].y - dy, p.orders[i].x - dx))
        size = math.ceil(len(ids) / k)
        chunks = [ids[i * size:(i + 1) * size] for i in range(k)]
        return [sorted(c, key=lambda i: (p.orders[i].w_start, p.orders[i].w_end)) for c in chunks]


class ManualEDD(_OneShot):
    name = "manual_edd"

    def _routes(self, p: Percept):
        k = self.cfg.n_couriers
        ids = sorted(p.orders, key=lambda i: (p.orders[i].w_start, p.orders[i].w_end))
        return [ids[i::k] for i in range(k)]
