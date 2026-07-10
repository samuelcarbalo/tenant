from .base import *
import os

DEBUG = True
print("========== DEVELOPMENT SETTINGS CARGADO ==========")  # Debug
# SQLite para desarrollo
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
# CORS
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


# Cache en memoria (sin Redis) — Channel layer usa InMemory para desarrollo local
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Email backend de consola
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Throttling más permisivo en desarrollo (evita bloqueos tras pruebas intensivas)
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
    "anon": "10000/day",
    "user": "10000/day",
}
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}