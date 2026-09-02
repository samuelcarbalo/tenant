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


def get_mp_config() -> dict[str, str | bool]:
    """
    Devuelve credenciales activas según is_production en admin.

    Fallback a variables de entorno si la fila singleton está vacía
    (migración gradual desde Render env vars).
    """
    cfg = MercadoPagoConfig.load()

    is_production = cfg.is_production
    if is_production:
        access_token = cfg.access_token_prod or getattr(
            settings, "MERCADOPAGO_ACCESS_TOKEN", ""
        )
        public_key = cfg.public_key_prod or getattr(
            settings, "MERCADOPAGO_PUBLIC_KEY", ""
        )
    else:
        access_token = cfg.access_token_test or getattr(
            settings, "MERCADOPAGO_ACCESS_TOKEN", ""
        )
        public_key = cfg.public_key_test or getattr(
            settings, "MERCADOPAGO_PUBLIC_KEY", ""
        )

    return {
        "is_production": is_production,
        "access_token": (access_token or "").strip(),
        "public_key": (public_key or "").strip(),
    }
