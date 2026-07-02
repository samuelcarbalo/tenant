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
