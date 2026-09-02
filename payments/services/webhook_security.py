"""
Validación de firmas de webhooks de Mercado Pago (x-signature / x-request-id).

Documentación oficial:
https://www.mercadopago.com.co/developers/es/docs/your-integrations/notifications/webhooks

Manifest:
  id:{data.id};request-id:{x-request-id};ts:{ts};
HMAC-SHA256 con el secreto del webhook → comparar con v1 de x-signature.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def extract_data_id(request) -> str | None:
    """Obtiene el id del recurso notificado (query o body JSON)."""
    data_id = request.query_params.get("data.id") or request.query_params.get("id")
    if data_id:
        return str(data_id)

    payload = request.data if hasattr(request, "data") else {}
    if isinstance(payload, dict):
        nested = payload.get("data") or {}
        if isinstance(nested, dict) and nested.get("id") is not None:
            return str(nested["id"])
        if payload.get("id") is not None:
            return str(payload["id"])
    return None


def parse_x_signature(header_value: str) -> dict[str, str]:
    """
    Parsea 'ts=1704908010,v1=abc...' → {'ts': '...', 'v1': '...'}.
    """
    parts: dict[str, str] = {}
    if not header_value:
        return parts
    for chunk in header_value.split(","):
        chunk = chunk.strip()
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parts[key.strip()] = value.strip()
    return parts


def build_manifest(*, data_id: str, request_id: str, ts: str) -> str:
    return f"id:{data_id};request-id:{request_id};ts:{ts};"


def verify_mercadopago_signature(
    *,
    x_signature: str,
    x_request_id: str,
    data_id: str,
    secret: str | None = None,
) -> bool:
    """
    Retorna True si la firma HMAC es válida.
    Si no hay secreto configurado en DEV, permite el webhook con warning
    (producción debe exigir secreto).
    """
    secret = secret if secret is not None else getattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "")
    enforce = getattr(settings, "MERCADOPAGO_WEBHOOK_ENFORCE_SIGNATURE", None)
    if enforce is None:
        enforce = not settings.DEBUG

    if not secret:
        if enforce:
            logger.error("MERCADOPAGO_WEBHOOK_SECRET no configurado; rechazando webhook.")
            return False
        logger.warning(
            "MERCADOPAGO_WEBHOOK_SECRET vacío — webhook aceptado sin firma (solo desarrollo)."
        )
        return True

    if not x_signature or not x_request_id or not data_id:
        logger.warning("Webhook MP incompleto: falta x-signature, x-request-id o data.id")
        return False

    parsed = parse_x_signature(x_signature)
    ts = parsed.get("ts", "")
    v1 = parsed.get("v1", "")
    if not ts or not v1:
        logger.warning("x-signature malformada: %s", x_signature)
        return False

    manifest = build_manifest(data_id=str(data_id), request_id=x_request_id, ts=ts)
    expected = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    valid = hmac.compare_digest(expected, v1)
    if not valid:
        logger.warning(
            "Firma MP inválida data_id=%s request_id=%s ts=%s",
            data_id,
            x_request_id,
            ts,
        )
    return valid


def signature_from_request(request) -> dict[str, Any]:
    """Helper para logs / auditoría."""
    return {
        "x_signature": request.headers.get("x-signature", "")
        or request.META.get("HTTP_X_SIGNATURE", ""),
        "x_request_id": request.headers.get("x-request-id", "")
        or request.META.get("HTTP_X_REQUEST_ID", ""),
        "data_id": extract_data_id(request),
    }
