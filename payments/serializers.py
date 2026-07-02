from rest_framework import serializers

from payments.models import PaymentOrder, TransaccionFacturacion
from payments.packages import CREDIT_PACKAGES


class CreditPackageSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    credits = serializers.IntegerField()
    price_cop = serializers.IntegerField()
    badge = serializers.CharField(allow_null=True)
    savings_cop = serializers.IntegerField()
    description = serializers.CharField()
    standard_price_cop = serializers.SerializerMethodField()

    def get_standard_price_cop(self, obj):
        return obj["credits"] * 1000


class CreatePreferenceSerializer(serializers.Serializer):
    package_id = serializers.ChoiceField(
        choices=list(CREDIT_PACKAGES.keys()),
        help_text="ID del paquete: basico, bronce, plata, oro",
    )


class PreferenceResponseSerializer(serializers.Serializer):
    preference_id = serializers.CharField()
    init_point = serializers.CharField(required=False, allow_null=True)
    sandbox_init_point = serializers.CharField(required=False, allow_null=True)
    order_id = serializers.UUIDField()


class PaymentOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentOrder
        fields = [
            "id",
            "package_id",
            "credits_amount",
            "amount_cop",
            "status",
            "credits_applied",
            "created_at",
        ]


class TransaccionFacturacionSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = TransaccionFacturacion
        fields = [
            "id",
            "user_email",
            "monto_total",
            "comision_mercado_pago",
            "iva_comision",
            "monto_neto_recibido",
            "creditos_comprados",
            "package_id",
            "mp_payment_id",
            "created_at",
        ]
