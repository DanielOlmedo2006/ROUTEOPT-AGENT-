"""Registro (log) de ejecución en JSON Lines: una línea por percepción, decisión, acción o resultado.

Cada línea lleva marca de tiempo real (ts, UTC) y del reloj simulado (sim_min / sim_hhmm).
Este archivo es la base de las pruebas de la Fase 3.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def hhmm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


class NullLogger:
    def log(self, kind: str, sim_t: float, **data):
        pass

    def close(self):
        pass


class JsonlLogger:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._f = open(path, "w", encoding="utf-8")

    def log(self, kind: str, sim_t: float, **data):
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "sim_min": round(sim_t, 2),
               "sim_hhmm": hhmm(sim_t), "kind": kind, **data}
        self._f.write(json.dumps(rec, ensure_ascii=False, default=float) + "\n")

    def close(self):
        self._f.close()
