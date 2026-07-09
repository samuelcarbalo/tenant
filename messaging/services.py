"""
Lógica de negocio para conversaciones reutilizables entre módulos.
"""
import bleach
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import (
    Conversation,
    ConversationParticipant,
    ConversationType,
    Message,
    MessageReadStatus,
)

ALLOWED_TAGS = []
ALLOWED_ATTRIBUTES = {}


def sanitize_message_body(body: str) -> str:
    """Sanitiza el contenido del mensaje contra XSS."""
    cleaned = bleach.clean(body.strip(), tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)
    return cleaned[:5000]


def get_or_create_conversation(
    *,
    organization,
    participants,
    content_object=None,
    conversation_type=ConversationType.GENERAL,
    subject="",
    initiated_by=None,
):
    """
    Obtiene o crea una conversación para un objeto de contexto y participantes.

    Args:
        organization: Organization instance
        participants: iterable de User (mínimo 2)
        content_object: instancia del modelo vinculado (JobOffer, RealEstateOffer, etc.)
        conversation_type: ConversationType value
        subject: título de la conversación
    """
    if len(participants) < 2:
        raise ValueError("Se requieren al menos 2 participantes.")

    content_type = None
    object_id = None
    if content_object is not None:
        content_type = ContentType.objects.get_for_model(content_object)
        object_id = content_object.pk

        lookup = {
            "organization": organization,
            "content_type": content_type,
            "object_id": object_id,
        }
        if initiated_by:
            lookup["initiated_by"] = initiated_by

        existing = Conversation.objects.filter(**lookup).first()
        if existing:
            _ensure_participants(existing, participants)
            return existing, False

    with transaction.atomic():
        conversation = Conversation.objects.create(
            organization=organization,
            subject=subject,
            conversation_type=conversation_type,
            content_type=content_type,
            object_id=object_id,
            initiated_by=initiated_by,
        )
        _ensure_participants(conversation, participants)
        return conversation, True


def _ensure_participants(conversation, participants):
    for user in participants:
        ConversationParticipant.objects.get_or_create(
            conversation=conversation,
            user=user,
        )


def create_job_application_conversation(application):
    """
    Crea conversación automática al postularse a una oferta laboral.
    Participantes: postulante + reclutador que publicó la oferta.
    """
    offer = application.offer
    participants = [application.applicant, offer.posted_by]
    subject = f"Postulación: {offer.title}"

    conversation, created = get_or_create_conversation(
        organization=offer.organization,
        participants=participants,
        content_object=application,
        conversation_type=ConversationType.JOB,
        subject=subject,
        initiated_by=application.applicant,
    )

    if created and application.cover_letter:
        send_message(
            conversation=conversation,
            sender=application.applicant,
            body=application.cover_letter,
        )

    return conversation


def create_real_estate_conversation(*, offer, interested_user):
    """
    Crea conversación entre interesado y propietario/agente de una propiedad.
    """
    participants = [interested_user, offer.posted_by]
    subject = f"Consulta: {offer.title}"

    conversation, created = get_or_create_conversation(
        organization=offer.organization,
        participants=participants,
        content_object=offer,
        conversation_type=ConversationType.REAL_ESTATE,
        subject=subject,
        initiated_by=interested_user,
    )
    return conversation, created


def send_message(*, conversation, sender, body, system_generated=False):
    """Envía un mensaje y actualiza metadatos de la conversación."""
    if not system_generated:
        body = sanitize_message_body(body)
        if not body:
            raise ValueError("El mensaje no puede estar vacío.")

    is_participant = ConversationParticipant.objects.filter(
        conversation=conversation,
        user=sender,
    ).exists()
    if not is_participant and not system_generated:
        raise PermissionError("No eres participante de esta conversación.")

    with transaction.atomic():
        message = Message.objects.create(
            conversation=conversation,
            sender=sender,
            body=body,
        )
        preview = body[:255] if len(body) <= 255 else body[:252] + "..."
        conversation.last_message_at = timezone.now()
        conversation.last_message_preview = preview
        conversation.save(update_fields=["last_message_at", "last_message_preview", "updated_at"])

    if not system_generated:
        _notify_chat_participants(conversation, sender, message, preview)

    return message


def _notify_chat_participants(conversation, sender, message, preview):
    from notifications.services import notify_chat_message

    participants = conversation.participants.select_related("user").exclude(user=sender)
    for p in participants:
        notify_chat_message(
            recipient=p.user,
            sender=sender,
            conversation_id=conversation.id,
            preview=preview,
        )


def mark_conversation_as_read(conversation, user):
    """Marca todos los mensajes de una conversación como leídos para un usuario."""
    now = timezone.now()
    participant = ConversationParticipant.objects.filter(
        conversation=conversation,
        user=user,
    ).first()
    if not participant:
        return

    participant.last_read_at = now
    participant.save(update_fields=["last_read_at", "updated_at"])

    unread_messages = conversation.messages.filter(
        is_deleted=False,
        created_at__lte=now,
    ).exclude(sender=user)

    if participant.last_read_at:
        # Solo mensajes nuevos desde la última lectura anterior
        pass

    read_records = [
        MessageReadStatus(message=msg, user=user, read_at=now)
        for msg in unread_messages
    ]
    MessageReadStatus.objects.bulk_create(read_records, ignore_conflicts=True)


def get_user_unread_total(user):
    """Total de mensajes no leídos del usuario en todas sus conversaciones."""
    total = 0
    participations = ConversationParticipant.objects.filter(
        user=user,
        conversation__is_active=True,
    ).select_related("conversation")
    for p in participations:
        total += p.unread_count
    return total


def user_can_access_conversation(user, conversation):
    """Verifica si el usuario es participante de la conversación."""
    if user.is_superuser:
        return True
    return ConversationParticipant.objects.filter(
        conversation=conversation,
        user=user,
    ).exists()
