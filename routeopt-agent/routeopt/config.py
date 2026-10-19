"""Parámetros del simulador y del agente (todo en un solo lugar para reproducibilidad)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # --- Entorno simulado (secciones 3, 4 y 5 del diseño) ---
    city_km: float = 12.0              # la ciudad es un cuadrado de 12 x 12 km
    depot: tuple = (6.0, 6.0)          # el depósito está en el centro
    n_couriers: int = 4                # flota piloto
    n_orders: int = 40                 # pedidos por jornada
    window_widths: tuple = (60.0, 90.0, 120.0)   # anchos posibles de ventana de tiempo (min)
    day_start: float = 480.0           # 08:00, en minutos desde 00:00
    bucket_min: float = 30.0           # franjas de 30 min para el perfil de tráfico
    n_buckets: int = 24                # 08:00-20:00
    zones_per_side: int = 3            # 3 x 3 = 9 zonas de tráfico
    road_factor: float = 1.3           # distancia por vía = 1,3 x distancia euclidiana
    base_speed_kmh: float = 30.0
    tick_min: float = 5.0              # ciclo percepción-decisión-acción cada 5 min simulados
    leg_sigma: float = 0.08            # ruido lognormal del tiempo de viaje (estocástico)
    service_sigma: float = 0.35        # ruido lognormal del tiempo de atención
    sensor_sigma: float = 0.05         # ruido del sensor de tráfico (parcialmente observable)
    gps_sigma_km: float = 0.03
    eta_sigma_min: float = 1.5
    incident_prob: float = 0.25        # prob. de que un repartidor sufra un incidente en la jornada
    incident_dur: tuple = (25.0, 45.0)
    event_prob_zone: float = 0.25      # prob. de congestión repentina por zona y jornada

    # --- Agente: función de utilidad U = -(w_dist*km + w_late_min*min_tarde + w_late_stop*n_tarde + w_load*horas_trabajo^2) ---
    w_dist: float = 1.0                # costo por km recorrido
    w_late_min: float = 0.8            # costo por minuto de retraso (llegar después de w_end)
    w_late_stop: float = 10.0          # costo fijo por parada tardía
    late_buffer_min: float = 2.0       # el agente planea llegar con este margen antes del cierre
    w_load: float = 8.0                # costo por (horas de trabajo)^2 de cada repartidor: reparte la carga
    tau_min: float = 40.0              # el sensor actual pesa menos a medida que se mira más al futuro
    restarts_init: int = 3             # reinicios aleatorios en la planificación inicial
    min_replan_gap: float = 15.0       # estabilidad: min. entre replanificaciones por riesgo
    replan_eps: float = 0.5            # mejora mínima de utilidad para aceptar un cambio opcional
    risk_max_late_min: float = 8.0     # disparador por riesgo: retraso previsto mayor a este valor
    max_ls_passes: int = 6
