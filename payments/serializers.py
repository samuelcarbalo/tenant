from rest_framework import serializers

from payments.models import MercadoPagoConfig, PaymentOrder, TransaccionFacturacion
from payments.packages import CREDIT_PACKAGES, CREDIT_VALUE_COP


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


class PurchaseHistorySerializer(serializers.ModelSerializer):
    """
    Serializer enriquecido para el historial de compras del usuario.
    Incluye nombre del paquete, descripción y mp_payment_id.
    """

    package_name = serializers.SerializerMethodField()
    package_description = serializers.SerializerMethodField()
    mp_payment_id = serializers.CharField(allow_null=True, allow_blank=True)
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = PaymentOrder
        fields = [
            "id",
            "package_id",
            "package_name",
            "package_description",
            "credits_amount",
            "amount_cop",
            "mp_payment_id",
            "status",
            "status_display",
            "credits_applied",
            "created_at",
            "updated_at",
        ]

    def get_package_name(self, obj: PaymentOrder) -> str:
        pkg = CREDIT_PACKAGES.get(obj.package_id)
        return pkg["name"] if pkg else obj.package_id

    def get_package_description(self, obj: PaymentOrder) -> str:
        pkg = CREDIT_PACKAGES.get(obj.package_id)
        if pkg:
            return f"{obj.credits_amount} créditos — {pkg['description']}"
        return f"{obj.credits_amount} créditos"

    def get_status_display(self, obj: PaymentOrder) -> str:
        return dict(PaymentOrder.STATUS_CHOICES).get(obj.status, obj.status)


class MercadoPagoConfigSerializer(serializers.ModelSerializer):
    """Lectura/escritura de credenciales MP (admin / superuser)."""

    class Meta:
        model = MercadoPagoConfig
        fields = [
            "is_production",
            "public_key_test",
            "access_token_test",
            "public_key_prod",
            "access_token_prod",
            "client_id_prod",
            "client_secret_prod",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


MercadoPagoConfigAdminSerializer = MercadoPagoConfigSerializer


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
