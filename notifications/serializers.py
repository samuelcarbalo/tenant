from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "type", "message", "read_at", "is_read", "extra_data", "created_at"]
        read_only_fields = fields


class NotificationCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["chat_message", "job_status_change"])
    message = serializers.CharField(max_length=500)
    extra_data = serializers.JSONField(required=False, default=dict)
