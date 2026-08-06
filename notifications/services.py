from django.utils import timezone

from .models import Notification, NotificationType
from .realtime import broadcast_notification


def _format_cop(amount) -> str:
    try:
        value = int(round(float(amount)))
    except (TypeError, ValueError):
        return str(amount)
    return f"${value:,}".replace(",", ".")


def create_notification(*, user, notification_type, message, extra_data=None):
    notification = Notification.objects.create(
        user=user,
        type=notification_type,
        message=message,
        extra_data=extra_data or {},
    )
    broadcast_notification(notification)
    return notification


def notify_chat_message(*, recipient, sender, conversation_id, preview):
    create_notification(
        user=recipient,
        notification_type=NotificationType.CHAT_MESSAGE,
        message=f"Nuevo mensaje de {sender.full_name or sender.username}: {preview[:120]}",
        extra_data={"link": f"/messages/{conversation_id}"},
    )


def notify_job_status_change(*, application):
    status_labels = dict(application.STATUS_CHOICES)
    label = status_labels.get(application.status, application.status)
    create_notification(
        user=application.applicant,
        notification_type=NotificationType.JOB_STATUS_CHANGE,
        message=f'Tu postulación a "{application.offer.title}" cambió a: {label}',
        extra_data={
            "link": f"/jobs/{application.offer_id}",
            "application_id": str(application.id),
            "status": application.status,
        },
    )


def notify_payment_success(
    *,
    user,
    credits: int,
    order_id: str,
    mp_payment_id: str,
    amount_cop=None,
):
    """Notificación in-app + push en vivo tras acreditar créditos."""
    amount_label = _format_cop(amount_cop) if amount_cop is not None else None
    if amount_label:
        message = (
            f"Se han acreditado {credits} créditos a tu cuenta "
            f"por un valor de {amount_label} COP."
        )
    else:
        message = f"Se han acreditado {credits} créditos a tu cuenta. ¡Ya puedes usarlos!"

    occurred_at = timezone.now().isoformat()
    return create_notification(
        user=user,
        notification_type=NotificationType.PAYMENT_SUCCESS,
        message=message,
        extra_data={
            "title": "¡Pago aprobado!",
            "link": "/creditos?tab=historial",
            "user_id": str(user.id),
            "order_id": str(order_id),
            "payment_id": str(mp_payment_id),
            "mp_payment_id": str(mp_payment_id),
            "amount": float(amount_cop) if amount_cop is not None else None,
            "credits_added": credits,
            "credits": credits,
            "status": "approved",
            "date": occurred_at,
        },
    )


def notify_payment_status(
    *,
    user,
    status: str,
    order_id: str | None = None,
    mp_payment_id: str | None = None,
    amount_cop=None,
    credits: int | None = None,
):
    """Notificaciones de estados no aprobados (pending / rejected)."""
    occurred_at = timezone.now().isoformat()
    amount_label = _format_cop(amount_cop) if amount_cop is not None else None

    if status in ("pending", "in_process", "authorized"):
        ntype = NotificationType.PAYMENT_PENDING
        title = "Pago pendiente"
        message = "Tu pago está pendiente de confirmación en Mercado Pago."
        if amount_label:
            message = f"Tu pago de {amount_label} COP está pendiente de confirmación."
    else:
        ntype = NotificationType.PAYMENT_FAILED
        title = "Pago rechazado"
        message = "Tu pago no pudo completarse. Puedes intentar de nuevo desde Créditos."
        if amount_label:
            message = (
                f"Tu pago de {amount_label} COP no pudo completarse. "
                "Intenta de nuevo desde Créditos."
            )

    return create_notification(
        user=user,
        notification_type=ntype,
        message=message,
        extra_data={
            "title": title,
            "link": "/creditos?tab=historial",
            "user_id": str(user.id),
            "order_id": str(order_id) if order_id else None,
            "payment_id": str(mp_payment_id) if mp_payment_id else None,
            "mp_payment_id": str(mp_payment_id) if mp_payment_id else None,
            "amount": float(amount_cop) if amount_cop is not None else None,
            "credits_added": credits,
            "credits": credits,
            "status": status,
            "date": occurred_at,
        },
    )
