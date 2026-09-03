from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Profile

User = get_user_model()


class ProfileSerializer(serializers.ModelSerializer):
    """Serializer de lectura para perfiles."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True,
    )

    class Meta:
        model = Profile
        fields = [
            "id",
            "user",
            "user_email",
            "user_name",
            "organization",
            "organization_name",
            "bio",
            "birth_date",
            "location",
            "department",
            "job_title",
            "dynamic_data",
            "avatar",
            "preferences",
            "completion_percentage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "organization",
            "completion_percentage",
            "created_at",
            "updated_at",
        ]


class ProfileCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer para crear/actualizar perfiles."""

    user_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    last_name = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Profile
        fields = [
            "bio",
            "birth_date",
            "location",
            "department",
            "job_title",
            "dynamic_data",
            "avatar",
            "preferences",
            "user_name",
            "first_name",
            "last_name",
        ]
        extra_kwargs = {
            "bio": {"required": False, "allow_blank": True},
            "location": {"required": False, "allow_blank": True},
            "department": {"required": False, "allow_blank": True},
            "job_title": {"required": False, "allow_blank": True},
            "birth_date": {"required": False, "allow_null": True},
            "avatar": {"required": False, "allow_blank": True, "max_length": 500},
            "preferences": {"required": False},
            "dynamic_data": {"required": False},
        }

    def validate_dynamic_data(self, value):
        """Validar campos dinámicos solo cuando el cliente los envía."""
        if value is None:
            return value

        request = self.context.get("request")
        organization = getattr(getattr(request, "user", None), "organization", None)
        if not organization:
            return value

        allowed_fields = {f["name"] for f in organization.get_profile_fields()}
        sent_fields = set(value.keys())
        invalid_fields = sent_fields - allowed_fields
        if invalid_fields:
            raise serializers.ValidationError(
                f"Campos no permitidos: {invalid_fields}. "
                f"Campos permitidos: {allowed_fields}"
            )

        is_valid, error = organization.validate_profile_data(value)
        if not is_valid:
            raise serializers.ValidationError(error)
        return value

    def _apply_user_fields(self, user, validated_data):
        user_name = validated_data.pop("user_name", serializers.empty)
        first_name = validated_data.pop("first_name", serializers.empty)
        last_name = validated_data.pop("last_name", serializers.empty)

        update_fields = []

        if user_name is not serializers.empty:
            parts = user_name.strip().split(None, 1)
            user.first_name = parts[0] if parts else ""
            user.last_name = parts[1] if len(parts) > 1 else ""
            update_fields.extend(["first_name", "last_name"])
        else:
            if first_name is not serializers.empty:
                user.first_name = first_name.strip()
                update_fields.append("first_name")
            if last_name is not serializers.empty:
                user.last_name = last_name.strip()
                update_fields.append("last_name")

        if update_fields:
            user.save(update_fields=list(dict.fromkeys(update_fields)))

    def update(self, instance, validated_data):
        self._apply_user_fields(instance.user, validated_data)

        if "dynamic_data" in validated_data:
            current_dynamic = instance.dynamic_data or {}
            current_dynamic.update(validated_data.pop("dynamic_data"))
            validated_data["dynamic_data"] = current_dynamic

        instance = super().update(instance, validated_data)
        instance.refresh_from_db()
        if hasattr(instance, "user"):
            instance.user.refresh_from_db()
        return instance

    def to_representation(self, instance):
        return ProfileSerializer(instance, context=self.context).data


class ProfileListSerializer(serializers.ModelSerializer):
    """Serializer optimizado para listados (campos mínimos)."""

    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Profile
        fields = [
            "id",
            "user_name",
            "user_email",
            "department",
            "job_title",
            "avatar",
            "completion_percentage",
        ]


class ProfileSearchSerializer(serializers.Serializer):
    """Serializer para búsqueda de perfiles."""

    query = serializers.CharField(required=True, min_length=2)
    department = serializers.CharField(required=False)
    fields = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
