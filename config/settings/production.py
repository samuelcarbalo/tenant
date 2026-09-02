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
        "Ejemplo: CORS_ALLOWED_ORIGINS=https://chever.co,https://www.chever.co"
    )
for _origin in ("https://chever.co", "https://www.chever.co"):
    if _origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_origin)
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS") or list(CORS_ALLOWED_ORIGINS)

# Orígenes permitidos para handshake WebSocket (Origin header del navegador).
WEBSOCKET_ALLOWED_ORIGINS = list(CORS_ALLOWED_ORIGINS)
_extra_ws_origins = _env_list("WEBSOCKET_ALLOWED_ORIGINS")
for _origin in _extra_ws_origins:
    if _origin not in WEBSOCKET_ALLOWED_ORIGINS:
        WEBSOCKET_ALLOWED_ORIGINS.append(_origin)

# Enlaces de correo (nunca localhost, aunque el env de Render esté mal).
_frontend = (os.getenv("FRONTEND_URL") or "https://chever.co").strip().rstrip("/")
if (
    not _frontend
    or "localhost" in _frontend
    or "127.0.0.1" in _frontend
):
    _frontend = "https://chever.co"
elif _frontend.startswith("http://") and "chever.co" in _frontend:
    _frontend = "https://chever.co"
FRONTEND_URL = _frontend

# ── Base de datos (PostgreSQL / Neon) ───────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "")
_DB_CONN_MAX_AGE = int(os.getenv("DB_CONN_MAX_AGE", "600"))
_DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
_DB_SSL_REQUIRE = _env_bool("DB_SSL_REQUIRE", True)


def _apply_postgres_options(db_config: dict) -> dict:
    """Pool persistente + timeout de conexión + SSL (Neon sslmode=require)."""
    db_config["CONN_MAX_AGE"] = _DB_CONN_MAX_AGE
    db_config["CONN_HEALTH_CHECKS"] = _env_bool("DB_CONN_HEALTH_CHECKS", True)
    options = db_config.setdefault("OPTIONS", {})
    options["connect_timeout"] = _DB_CONNECT_TIMEOUT
    if _DB_SSL_REQUIRE and "sslmode" not in options:
        options["sslmode"] = "require"
    return db_config


if DATABASE_URL:
    DATABASES = {
        "default": _apply_postgres_options(
            dj_database_url.config(
                default=DATABASE_URL,
                conn_max_age=_DB_CONN_MAX_AGE,
                ssl_require=_DB_SSL_REQUIRE,
            )
        )
    }
else:
    _fallback_options = {"connect_timeout": _DB_CONNECT_TIMEOUT}
    if _DB_SSL_REQUIRE:
        _fallback_options["sslmode"] = "require"
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", ""),
            "USER": os.getenv("POSTGRES_USER", ""),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": _DB_CONN_MAX_AGE,
            "CONN_HEALTH_CHECKS": _env_bool("DB_CONN_HEALTH_CHECKS", True),
            "OPTIONS": _fallback_options,
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
# SMTP está bloqueado en Render Free (Errno 101 en 587 y 465).
# El envío real usa core.email.send_system_email → API HTTP de Resend (:443).
EMAIL_BACKEND = "core.mail_backends.ResendHTTPEmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = 443
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False
DEFAULT_FROM_EMAIL = (
    os.getenv("RESEND_FROM_EMAIL")
    or os.getenv("DEFAULT_FROM_EMAIL")
    or "Chéver <soporte@chever.co>"
)
if "gmail.com" in DEFAULT_FROM_EMAIL.lower() or "googlemail.com" in DEFAULT_FROM_EMAIL.lower():
    DEFAULT_FROM_EMAIL = "Chéver <soporte@chever.co>"
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

RESEND_API_KEY = (os.getenv("RESEND_API_KEY") or "").strip()
SENDGRID_API_KEY = (os.getenv("SENDGRID_API_KEY") or "").strip()
ANYMAIL = {"RESEND_API_KEY": RESEND_API_KEY} if RESEND_API_KEY else {}
EMAIL_LOGO_URL = os.getenv("EMAIL_LOGO_URL", "https://chever.co/chever_oficial.svg")

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