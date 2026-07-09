import logging

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from payments.models import PaymentOrder, TransaccionFacturacion
from payments.packages import CREDIT_PACKAGES, get_package
from payments.serializers import (
    CreatePreferenceSerializer,
    CreditPackageSerializer,
    PaymentOrderSerializer,
    TransaccionFacturacionSerializer,
)
from payments.services.mercadopago_service import MercadoPagoService
from payments.services.payment_processor import apply_approved_payment

logger = logging.getLogger(__name__)


class PaymentViewSet(viewsets.ViewSet):
    """Endpoints de compra de créditos vía Mercado Pago Checkout Pro."""

    permission_classes = [IsAuthenticated]

    @action(
        detail=False,
        methods=["get"],
        url_path="packages",
        permission_classes=[AllowAny],
    )
    def packages(self, request):
        packages = list(CREDIT_PACKAGES.values())
        serializer = CreditPackageSerializer(packages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="create-preference")
    def create_preference(self, request):
        serializer = CreatePreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        package_id = serializer.validated_data["package_id"]
        package = get_package(package_id)

        order = PaymentOrder.objects.create(
            user=request.user,
            package_id=package_id,
            credits_amount=package["credits"],
            amount_cop=package["price_cop"],
        )

        try:
            mp = MercadoPagoService()
            pref = mp.create_preference(
                package_id=package_id,
                user_email=request.user.email,
                user_id=str(request.user.id),
                order_id=str(order.id),
            )
        except Exception as exc:
            order.status = "cancelled"
            order.save(update_fields=["status"])
            logger.exception("Error creating MP preference")
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        order.mp_preference_id = pref["preference_id"]
        order.save(update_fields=["mp_preference_id"])

        return Response(
            {
                "preference_id": pref["preference_id"],
                "init_point": pref.get("init_point"),
                "sandbox_init_point": pref.get("sandbox_init_point"),
                "order_id": order.id,
            }
        )

    @action(detail=False, methods=["get"], url_path="my-orders")
    def my_orders(self, request):
        orders = PaymentOrder.objects.filter(user=request.user)[:20]
        return Response(PaymentOrderSerializer(orders, many=True).data)

    @action(
        detail=False,
        methods=["get"],
        url_path="billing",
        permission_classes=[IsAdminUser],
    )
    def billing(self, request):
        txs = TransaccionFacturacion.objects.select_related("user")[:100]
        return Response(TransaccionFacturacionSerializer(txs, many=True).data)


@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def mercadopago_webhook(request):
    """
    Webhook de Mercado Pago para eventos de pago.
    MP envía ?topic=payment&id=PAYMENT_ID o body JSON según configuración.
    """
    topic = request.query_params.get("topic") or request.data.get("type", "")
    payment_id = request.query_params.get("id") or request.data.get("data", {}).get("id")

    if request.data.get("action") == "payment.updated":
        payment_id = request.data.get("data", {}).get("id")

    if topic not in ("payment", "") and not payment_id:
        return Response({"status": "ignored"})

    if not payment_id:
        return Response({"status": "no_payment_id"})

    try:
        mp = MercadoPagoService()
        payment = mp.get_payment(str(payment_id))
    except Exception:
        logger.exception("Webhook: failed to fetch payment %s", payment_id)
        return Response({"status": "error"}, status=status.HTTP_200_OK)

    if payment.get("status") != "approved":
        return Response({"status": payment.get("status", "unknown")})

    external_ref = payment.get("external_reference")
    if not external_ref:
        logger.warning("Webhook: payment %s without external_reference", payment_id)
        return Response({"status": "no_reference"})

    try:
        order = PaymentOrder.objects.get(id=external_ref)
    except PaymentOrder.DoesNotExist:
        logger.warning("Webhook: order not found %s", external_ref)
        return Response({"status": "order_not_found"})

    applied = apply_approved_payment(order, str(payment_id))
    return Response({"status": "approved" if applied else "already_applied"})


@api_view(["GET"])
@permission_classes([AllowAny])
def mp_public_config(request):
    """Expone la Public Key al frontend (seguro — es pública)."""
    return Response(
        {
            "public_key": getattr(settings, "MERCADOPAGO_PUBLIC_KEY", ""),
        }
    )
