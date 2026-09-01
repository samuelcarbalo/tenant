from rest_framework import serializers

from ecommerce.models import StoreSettings


class StoreSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSettings
        fields = ["id", "store_logo", "updated_at"]
        read_only_fields = ["id", "updated_at"]
        extra_kwargs = {
            "store_logo": {"allow_blank": True, "allow_null": True, "required": False},
        }

    def validate_store_logo(self, value):
        return value or ""
