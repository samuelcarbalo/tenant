"""Resolución de credenciales Mercado Pago (DB + fallback env)."""

from __future__ import annotations

from django.conf import settings

from payments.models import MercadoPagoConfig


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
