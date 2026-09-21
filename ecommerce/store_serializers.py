from decimal import Decimal

from rest_framework import serializers

from ecommerce.models import StoreSettings


class StoreSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSettings
        fields = ["id", "store_logo", "shipping_cost_cop", "updated_at"]
        read_only_fields = ["id", "updated_at"]
        extra_kwargs = {
            "store_logo": {"allow_blank": True, "allow_null": True, "required": False},
            "shipping_cost_cop": {"required": False, "min_value": Decimal("0")},
        }

    def validate_store_logo(self, value):
        return value or ""

    def validate_shipping_cost_cop(self, value):
        amount = Decimal(str(value or 0))
        if amount < 0:
            raise serializers.ValidationError("El costo de envío no puede ser negativo.")
        return amount.quantize(Decimal("1"))
