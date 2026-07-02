import uuid
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from authentication.models import User
from core.models import TimeStampedModel
from organizations.models import Organization


class ConversationType(models.TextChoices):
    JOB = "job", "Empleo"
    REAL_ESTATE = "real_estate", "Bienes Raíces"
    GENERAL = "general", "General"


class Conversation(TimeStampedModel):
    """
    Conversación privada vinculada a un objeto de contexto (oferta laboral,
    propiedad inmobiliaria, etc.) mediante GenericForeignKey.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    subject = models.CharField(max_length=255, blank=True)
    conversation_type = models.CharField(
        max_length=20,
        choices=ConversationType.choices,
        default=ConversationType.GENERAL,
        db_index=True,
    )

    # Relación polimórfica al objeto de contexto
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    object_id = models.UUIDField(null=True, blank=True, db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # Usuario que inició la conversación (p.ej. postulante o comprador interesado)
    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_conversations",
    )

    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_preview = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "messaging_conversations"
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "conversation_type"]),
            models.Index(fields=["content_type", "object_id"]),
        ]
        constraints = [
            # Una conversación por postulación (JobApplication) o por interesado+propiedad
            models.UniqueConstraint(
                fields=["content_type", "object_id", "initiated_by"],
                condition=models.Q(content_type__isnull=False, object_id__isnull=False),
                name="unique_conversation_per_context_initiator",
            ),
        ]

    def __str__(self):
        return self.subject or f"Conversación {self.id}"


class ConversationParticipant(TimeStampedModel):
    """Participante de una conversación con estado de lectura."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="conversation_participations",
    )
    last_read_at = models.DateTimeField(null=True, blank=True)
    is_muted = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "messaging_participants"
        unique_together = [["conversation", "user"]]
        indexes = [
            models.Index(fields=["user", "conversation"]),
        ]

    def __str__(self):
        return f"{self.user.email} en {self.conversation_id}"

    @property
    def unread_count(self):
        qs = self.conversation.messages.filter(is_deleted=False)
        if self.last_read_at:
            qs = qs.filter(created_at__gt=self.last_read_at)
        return qs.exclude(sender=self.user).count()


class Message(TimeStampedModel):
    """Mensaje individual dentro de una conversación."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    body = models.TextField()
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "messaging_messages"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["conversation", "is_deleted", "created_at"]),
        ]

    def __str__(self):
        preview = self.body[:50] if self.body else ""
        return f"Mensaje de {self.sender.email}: {preview}"


class MessageReadStatus(TimeStampedModel):
    """
    Estado de lectura por mensaje (read receipts).
    Complementa last_read_at del participante para indicadores granulares.
    """

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="read_statuses",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="message_read_statuses",
    )
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "messaging_message_read_status"
        unique_together = [["message", "user"]]
        indexes = [
            models.Index(fields=["user", "read_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} leyó mensaje {self.message_id}"
