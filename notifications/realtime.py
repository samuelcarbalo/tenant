"""Broadcast de notificaciones in-app vía Django Channels."""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def user_notifications_group(user_id) -> str:
    return f"notifications_user_{user_id}"


def serialize_notification_payload(notification) -> dict:
    return {
        "id": str(notification.id),
        "type": notification.type,
        "message": notification.message,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "is_read": notification.is_read,
        "extra_data": notification.extra_data or {},
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


def broadcast_notification(notification) -> None:
    """
    Empuja la notificación al grupo WebSocket del usuario.
    Si Redis/Channels no está disponible, solo se registra el error (la fila en DB ya existe).
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    group = user_notifications_group(notification.user_id)
    payload = serialize_notification_payload(notification)
    try:
        async_to_sync(channel_layer.group_send)(
            group,
            {"type": "notification.new", "notification": payload},
        )
    except Exception:
        logger.exception(
            "No se pudo emitir notification.new a %s (id=%s)",
            group,
            notification.id,
        )
