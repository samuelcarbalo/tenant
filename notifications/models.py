from django.db import models
from django.utils import timezone

from authentication.models import User
from core.models import TimeStampedModel


class NotificationType(models.TextChoices):
    CHAT_MESSAGE = "chat_message", "Mensaje de chat"
    JOB_STATUS_CHANGE = "job_status_change", "Cambio estado postulación"
    PAYMENT_SUCCESS = "payment_success", "Pago aprobado"
    PAYMENT_PENDING = "payment_pending", "Pago pendiente"
    PAYMENT_FAILED = "payment_failed", "Pago fallido"


class Notification(TimeStampedModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=30, choices=NotificationType.choices, db_index=True)
    message = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    extra_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "read_at", "created_at"]),
        ]

    @property
    def is_read(self):
        return self.read_at is not None

    def mark_read(self):
        if not self.read_at:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at", "updated_at"])
