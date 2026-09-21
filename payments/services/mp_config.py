"""Resolución de credenciales Mercado Pago (DB + fallback env)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

from payments.models import MercadoPagoConfig

logger = logging.getLogger(__name__)

EMPTY_MP_ADMIN_CONFIG = {
    "is_production": False,
    "public_key_test": "",
    "access_token_test": "",
    "public_key_prod": "",
    "access_token_prod": "",
    "client_id_prod": "",
    "client_secret_prod": "",
    "updated_at": None,
}


def _safe_rollback() -> None:
    try:
        connection.rollback()
    except Exception:  # noqa: BLE001
        pass


def _try_create_mp_config_table() -> bool:
    table = MercadoPagoConfig._meta.db_table
    try:
        existing = set(connection.introspection.table_names())
        if table not in existing:
            with connection.schema_editor() as editor:
                editor.create_model(MercadoPagoConfig)
            logger.warning("Tabla %s creada en caliente (schema ausente).", table)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("No se pudo crear la tabla %s: %s", table, exc)
        _safe_rollback()
        return False


def get_or_create_mp_config() -> MercadoPagoConfig | None:
    """
    Singleton id=1. Si la tabla no existe aún, intenta crearla y reintenta.
    Devuelve None si el schema sigue indisponible (el caller responde 200 controlado).
    """
    defaults = {"is_production": False}
    try:
        config, _ = MercadoPagoConfig.objects.get_or_create(id=1, defaults=defaults)
        return config
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("mercadopago_config no disponible: %s", exc)
        _safe_rollback()
        if not _try_create_mp_config_table():
            return None
        try:
            config, _ = MercadoPagoConfig.objects.get_or_create(id=1, defaults=defaults)
            return config
        except (OperationalError, ProgrammingError) as exc2:
            logger.warning("Reintento get_or_create mercadopago_config falló: %s", exc2)
            _safe_rollback()
            return None


def _setting(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _looks_test(value: str) -> bool:
    return value.upper().startswith("TEST-")


def _looks_live(value: str) -> bool:
    return value.upper().startswith("APP_USR-")


def _compatible(value: str, *, is_production: bool) -> str:
    """
    Evita mezclar credenciales TEST y LIVE.
    Prefijos oficiales MP: TEST- (sandbox) y APP_USR- (producción).
    """
    value = (value or "").strip()
    if not value:
        return ""
    if is_production and _looks_test(value):
        logger.error("Se omitió credencial TEST- en modo producción.")
        return ""
    if not is_production and _looks_live(value):
        logger.error("Se omitió credencial LIVE (APP_USR-) en modo sandbox.")
        return ""
    return value


def _first_compatible(*values: str, is_production: bool) -> str:
    for raw in values:
        compatible = _compatible(raw, is_production=is_production)
        if compatible:
            return compatible
    return ""


def _env_flag(name: str) -> bool:
    return _setting(name).lower() in ("1", "true", "yes", "on")


def get_mp_config() -> dict[str, str | bool]:
    """
    Devuelve credenciales activas según is_production en admin.

    Orden de resolución por entorno:
      1) Campos DB del modo activo (test o prod)
      2) Variables de entorno específicas (_TEST / _PROD)
      3) Fallback genérico MERCADOPAGO_ACCESS_TOKEN / PUBLIC_KEY de Render
         solo si el prefijo coincide con el modo activo
    """
    cfg = None
    try:
        cfg = MercadoPagoConfig.load()
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("mercadopago_config no disponible, usando env: %s", exc)
        _safe_rollback()

    is_production = bool(cfg.is_production) if cfg is not None else _env_flag("MERCADOPAGO_IS_PRODUCTION")

    if is_production:
        access_token = _first_compatible(
            (cfg.access_token_prod if cfg else ""),
            _setting("MERCADOPAGO_ACCESS_TOKEN_PROD"),
            _setting("MERCADOPAGO_ACCESS_TOKEN"),
            is_production=True,
        )
        public_key = _first_compatible(
            (cfg.public_key_prod if cfg else ""),
            _setting("MERCADOPAGO_PUBLIC_KEY_PROD"),
            _setting("MERCADOPAGO_PUBLIC_KEY"),
            is_production=True,
        )
    else:
        access_token = _first_compatible(
            (cfg.access_token_test if cfg else ""),
            _setting("MERCADOPAGO_ACCESS_TOKEN_TEST"),
            _setting("MERCADOPAGO_ACCESS_TOKEN"),
            is_production=False,
        )
        public_key = _first_compatible(
            (cfg.public_key_test if cfg else ""),
            _setting("MERCADOPAGO_PUBLIC_KEY_TEST"),
            _setting("MERCADOPAGO_PUBLIC_KEY"),
            is_production=False,
        )

    return {
        "is_production": is_production,
        "access_token": access_token,
        "public_key": public_key,
    }
