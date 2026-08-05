from .models import Notification, NotificationType


def create_notification(*, user, notification_type, message, extra_data=None):
    return Notification.objects.create(
        user=user,
        type=notification_type,
        message=message,
        extra_data=extra_data or {},
    )


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


def notify_payment_success(*, user, credits: int, order_id: str, mp_payment_id: str):
    """Notificación in-app tras acreditar créditos (historial PWA)."""
    return create_notification(
        user=user,
        notification_type=NotificationType.PAYMENT_SUCCESS,
        message=f"Se acreditaron {credits} créditos a tu cuenta. ¡Ya puedes usarlos!",
        extra_data={
            "link": "/creditos",
            "order_id": str(order_id),
            "mp_payment_id": str(mp_payment_id),
            "credits": credits,
            "status": "approved",
        },
    )


def notify_payment_status(*, user, status: str, order_id: str | None = None, mp_payment_id: str | None = None):
    """Notificaciones de estados no aprobados (pending / rejected)."""
    if status in ("pending", "in_process", "authorized"):
        ntype = NotificationType.PAYMENT_PENDING
        message = "Tu pago está pendiente de confirmación en Mercado Pago."
    else:
        ntype = NotificationType.PAYMENT_FAILED
        message = "Tu pago no pudo completarse. Puedes intentar de nuevo desde Créditos."

    return create_notification(
        user=user,
        notification_type=ntype,
        message=message,
        extra_data={
            "link": "/creditos",
            "order_id": str(order_id) if order_id else None,
            "mp_payment_id": str(mp_payment_id) if mp_payment_id else None,
            "status": status,
        },
    )
