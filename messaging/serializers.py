from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from authentication.models import User
from .models import Conversation, ConversationParticipant, Message, MessageReadStatus


class UserMinimalSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "username", "first_name", "last_name", "full_name", "company_name", "user_type"]
        read_only_fields = fields

    def get_full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name or obj.username


class ConversationParticipantSerializer(serializers.ModelSerializer):
    user = UserMinimalSerializer(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ConversationParticipant
        fields = ["id", "user", "last_read_at", "unread_count", "joined_at", "is_muted"]


class MessageSerializer(serializers.ModelSerializer):
    sender = UserMinimalSerializer(read_only=True)
    is_own = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "conversation",
            "sender",
            "body",
            "is_edited",
            "edited_at",
            "is_deleted",
            "created_at",
            "is_own",
        ]
        read_only_fields = [
            "id",
            "conversation",
            "sender",
            "is_edited",
            "edited_at",
            "is_deleted",
            "created_at",
            "is_own",
        ]

    def get_is_own(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.sender_id == request.user.id
        return False


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000, trim_whitespace=True)


class MessageUpdateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000, trim_whitespace=True)


class ConversationContextSerializer(serializers.Serializer):
    """Metadatos del objeto vinculado (oferta laboral, propiedad, etc.)."""

    type = serializers.CharField()
    id = serializers.UUIDField()
    title = serializers.CharField()
    subtitle = serializers.CharField(required=False, allow_blank=True)
    url_path = serializers.CharField(required=False, allow_blank=True)


class ConversationListSerializer(serializers.ModelSerializer):
    participants = ConversationParticipantSerializer(many=True, read_only=True)
    other_participant = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    context = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "subject",
            "conversation_type",
            "last_message_at",
            "last_message_preview",
            "participants",
            "other_participant",
            "unread_count",
            "context",
            "created_at",
        ]

    def get_other_participant(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        for p in obj.participants.all():
            if p.user_id != request.user.id:
                return UserMinimalSerializer(p.user).data
        return None

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0
        for p in obj.participants.all():
            if p.user_id == request.user.id:
                return p.unread_count
        return 0

    def get_context(self, obj):
        if not obj.content_object:
            return None
        return _build_context(obj)


class ConversationDetailSerializer(ConversationListSerializer):
    class Meta(ConversationListSerializer.Meta):
        fields = ConversationListSerializer.Meta.fields + ["updated_at"]


class ConversationCreateSerializer(serializers.Serializer):
    conversation_type = serializers.ChoiceField(
        choices=["job", "real_estate", "general"],
        default="general",
    )
    content_type_model = serializers.CharField(required=False, allow_blank=True)
    object_id = serializers.UUIDField(required=False)
    participant_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=10,
    )
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True)
    initial_message = serializers.CharField(max_length=5000, required=False, allow_blank=True)


def _build_context(conversation):
    """Construye metadatos de contexto según el tipo de objeto vinculado."""
    obj = conversation.content_object
    if obj is None:
        return None

    model_name = conversation.content_type.model

    if model_name == "jobapplication":
        offer = obj.offer
        return {
            "type": "job_application",
            "id": str(obj.id),
            "title": offer.title,
            "subtitle": offer.company_name,
            "url_path": f"/jobs/{offer.id}",
            "offer_id": str(offer.id),
            "application_status": obj.status,
        }

    if model_name == "joboffer":
        return {
            "type": "job",
            "id": str(obj.id),
            "title": obj.title,
            "subtitle": obj.company_name,
            "url_path": f"/jobs/{obj.id}",
        }

    if model_name == "realestateoffer":
        return {
            "type": "real_estate",
            "id": str(obj.id),
            "title": obj.title,
            "subtitle": f"{obj.price} {obj.currency}",
            "url_path": f"/real-estate/{obj.id}",
        }

    return {
        "type": model_name,
        "id": str(obj.pk),
        "title": str(obj),
        "subtitle": "",
    }
