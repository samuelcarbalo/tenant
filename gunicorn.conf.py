"""Gunicorn + UvicornWorker (ASGI: HTTP + WebSocket) con graceful shutdown."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
worker_class = "uvicorn.workers.UvicornWorker"

# Tiempo máximo por petición HTTP (cold start / queries pesadas).
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "90"))
# Tras SIGTERM (deploy Render): espera conexiones activas antes de forzar cierre.
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "120"))

# Logs a stdout (contenedores Render).
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Preload desactivado: Channels/WebSocket + ASGI no son seguros con fork post-preload.
preload_app = False
