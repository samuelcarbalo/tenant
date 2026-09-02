"""
ASGI config for config project with Django Channels support.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.core.asgi import get_asgi_application

# Usa la variable de entorno que le pases, no hardcodear 'development'
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

django_asgi_app = get_asgi_application()

# Importaciones post-setup (evitan AppRegistryNotReady)
from django.conf import settings  # noqa: E402

from messaging.middleware import JWTAuthMiddlewareStack  # noqa: E402
from messaging.routing import websocket_urlpatterns as messaging_ws  # noqa: E402
from notifications.routing import websocket_urlpatterns as notifications_ws  # noqa: E402

websocket_urlpatterns = messaging_ws + notifications_ws


def _websocket_allowed_origins() -> list[str]:
    origins = list(getattr(settings, "WEBSOCKET_ALLOWED_ORIGINS", []) or [])
    if origins:
        return origins

    cors_origins = list(getattr(settings, "CORS_ALLOWED_ORIGINS", []) or [])
    frontend = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    if frontend and frontend not in cors_origins:
        cors_origins.append(frontend)
    return cors_origins


_ws_stack = JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
_allowed_origins = _websocket_allowed_origins()
if _allowed_origins:
    _ws_stack = OriginValidator(_ws_stack, _allowed_origins)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": _ws_stack,
    }
)
