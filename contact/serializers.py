from rest_framework import serializers

from .models import ContactMessage


class ContactMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "subject", "message"]

    def validate_message(self, value):
        cleaned = (value or "").strip()
        if len(cleaned) < 10:
            raise serializers.ValidationError(
                "El mensaje debe tener al menos 10 caracteres."
            )
        return cleaned

    def validate_name(self, value):
        cleaned = (value or "").strip()
        if len(cleaned) < 2:
            raise serializers.ValidationError("Indica tu nombre.")
        return cleaned


class ContactMessageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["is_read"]


class ContactMessageSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True, default=None
    )
    user_email = serializers.EmailField(
        source="user.email", read_only=True, default=None
    )

    class Meta:
        model = ContactMessage
        fields = [
            "id",
            "name",
            "email",
            "subject",
            "message",
            "is_read",
            "organization",
            "organization_name",
            "user",
            "user_email",
            "ip_address",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
