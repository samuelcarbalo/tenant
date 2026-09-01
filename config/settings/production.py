"""Configuración de producción.

Todo lo sensible/variable se lee de variables de entorno (tenant/.env o el
entorno del servidor). Ver .env.example para la lista completa.

Ejecutar con:  DJANGO_SETTINGS_MODULE=config.settings.production
"""
import os
import dj_database_url
from .base import *  # noqa: F401,F403

# Garantiza ecommerce en producción (hereda de base; refuerzo explícito).
if "ecommerce" not in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS.append("ecommerce")  # noqa: F405


def _env_list(name, default=""):
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ── Núcleo ──────────────────────────────────────────────────────────────────
DEBUG = False

if not SECRET_KEY:  # noqa: F405 (viene de base)
    raise RuntimeError("SECRET_KEY es obligatorio en producción (define la variable de entorno).")

ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS es obligatorio en producción (lista separada por comas).")

# ── CORS / CSRF ─────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS")
if not CORS_ALLOWED_ORIGINS:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS es obligatorio en producción. "
        "Ejemplo: CORS_ALLOWED_ORIGINS=https://missigdigital.site,https://https://missingdigitalback.onrender.com/"
    )
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS") or CORS_ALLOWED_ORIGINS

# ── Base de datos (PostgreSQL) ──────────────────────────────────────────────

# Intenta leer una sola URL (ideal para Neon). Si no existe, recurre al desglose tradicional.
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "600")),
            ssl_require=_env_bool("DB_SSL_REQUIRE", True),
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", ""),
            "USER": os.getenv("POSTGRES_USER", ""),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        }
    }
# ── Cache + Channel layer (Redis) ───────────────────────────────────────────
# ── Cache + Channel layer ──────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "")

if REDIS_URL and "127.0.0.1" not in REDIS_URL and "localhost" not in REDIS_URL:
    # Redis real configurado
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    # Fallback seguro: memoria local
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

# El throttling usa la cache: en prod comparte contadores vía Redis.

# ── Archivos estáticos (WhiteNoise) ─────────────────────────────────────────
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Insertar WhiteNoise justo después de SecurityMiddleware
_wn = "whitenoise.middleware.WhiteNoiseMiddleware"
if _wn not in MIDDLEWARE:  # noqa: F405
    try:
        _idx = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")  # noqa: F405
        MIDDLEWARE.insert(_idx + 1, _wn)  # noqa: F405
    except ValueError:
        MIDDLEWARE.insert(0, _wn)  # noqa: F405

# ── Email (producción / Render) ─────────────────────────────────────────────
# Render Free bloquea tráfico saliente a smtp.gmail.com:587 (Errno 101).
# Por defecto usamos SMTPS 465. Si EMAIL_PORT=587 quedó en el dashboard, se
# fuerza a 465. Si 465 también está filtrado, define RESEND_API_KEY (HTTPS).
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
_email_port = int(os.getenv("EMAIL_PORT", "465") or "465")
if _email_port == 587:
    _email_port = 465
EMAIL_PORT = _email_port
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "True").lower() == "true"
if EMAIL_PORT == 465:
    EMAIL_USE_SSL = True
    EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER) or DEFAULT_FROM_EMAIL  # noqa: F405
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

RESEND_API_KEY = (os.getenv("RESEND_API_KEY") or "").strip()
SENDGRID_API_KEY = (os.getenv("SENDGRID_API_KEY") or "").strip()
if RESEND_API_KEY:
    # HTTPS: no depende de smtplib ni de los puertos 587/465.
    try:
        import anymail  # noqa: F401

        if "anymail" not in INSTALLED_APPS:  # noqa: F405
            INSTALLED_APPS.append("anymail")  # noqa: F405
        EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
        ANYMAIL = {"RESEND_API_KEY": RESEND_API_KEY}
    except ImportError:
        EMAIL_BACKEND = "core.mail_backends.ResendHTTPEmailBackend"
elif SENDGRID_API_KEY:
    try:
        import anymail  # noqa: F401

        if "anymail" not in INSTALLED_APPS:  # noqa: F405
            INSTALLED_APPS.append("anymail")  # noqa: F405
        EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
        ANYMAIL = {"SENDGRID_API_KEY": SENDGRID_API_KEY}
    except ImportError:
        pass

# ── Seguridad HTTPS ─────────────────────────────────────────────────────────
# Detrás de un proxy/balanceador que hace TLS (nginx, traefik, load balancer):
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ── Logging (a stdout, apto para contenedores) ──────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "payments": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# ── Monitoreo de errores (Sentry, opcional) ─────────────────────────────────
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_RATE", "0.1")),
            send_default_pii=False,
            environment=os.getenv("SENTRY_ENV", "production"),
        )
    except ImportError:
        pass
# Al final de production.py
print("=" * 60)
print("DEBUG CORS:")
print("CORS_ALLOWED_ORIGINS raw env:", os.getenv("CORS_ALLOWED_ORIGINS", "NO SET"))
print("CORS_ALLOWED_ORIGINS parsed:", CORS_ALLOWED_ORIGINS)
print("=" * 60)