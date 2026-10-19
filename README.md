
# ROUTEOPT-AGENT

Agente de optimización de rutas con planificación por utilidad, replanificación ante eventos y
aprendizaje del tráfico y de los tiempos de servicio. El entorno es un simulador local; no requiere
servicios externos ni claves de API.

## Interfaz web

Instala las dependencias y arranca la demostración interactiva desde la raíz del repositorio:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

En el panel lateral puedes elegir el tamaño de la flota, pedidos, semilla y jornadas. La vista permite
examinar las rutas ejecutadas, las decisiones y acciones del agente, el tráfico percibido, las métricas
por jornada y la comparación opcional con planificadores manuales. La misma semilla y día generan el
mismo escenario para todas las variantes.

La interfaz ejecuta el simulador existente en `routeopt/`; no sustituye el agente por una simulación
visual. El runner de consola sigue disponible con `python -m routeopt`.
