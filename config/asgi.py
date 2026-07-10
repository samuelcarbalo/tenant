"""
ASGI config for config project with Django Channels support.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# Usa la variable de entorno que le pases, no hardcodear 'development'
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

django_asgi_app = get_asgi_application()

# Importaciones post-setup (evitan AppRegistryNotReady)
from messaging.middleware import JWTAuthMiddlewareStack  # noqa: E402
from messaging.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)