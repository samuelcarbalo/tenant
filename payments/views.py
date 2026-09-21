import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from core.permissions import IsSuperUser, user_admin_level, user_is_platform_elevated
from payments.models import MercadoPagoWebhookEvent, PaymentOrder, TransaccionFacturacion
from payments.packages import CREDIT_PACKAGES, get_package
from payments.serializers import (
    CreatePreferenceSerializer,
    CreditPackageSerializer,
    MercadoPagoConfigSerializer,
    PaymentOrderSerializer,
    PurchaseHistorySerializer,
    TransaccionFacturacionSerializer,
)
from payments.services.billing import public_processing_breakdown
from payments.services.mercadopago_service import MercadoPagoService
from payments.services.mp_config import (
    EMPTY_MP_ADMIN_CONFIG,
    get_mp_config,
    get_or_create_mp_config,
)
from payments.services.webhook_processor import dispatch_webhook_processing
from payments.services.webhook_security import (
    extract_data_id,
    signature_from_request,
    verify_mercadopago_signature,
)

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
        if not package:
            return Response(
                {"detail": "Paquete no encontrado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        breakdown = public_processing_breakdown(package["price_cop"])

        order = PaymentOrder.objects.create(
            user=request.user,
            package_id=package_id,
            credits_amount=package["credits"],
            amount_cop=breakdown["total_amount"],
        )

        try:
            mp = MercadoPagoService()
            pref = mp.create_preference(
                package_id=package_id,
                user_email=request.user.email,
                user_id=str(request.user.id),
                order_id=str(order.id),
                base_amount=breakdown["base_amount"],
                fee_amount=breakdown["fee_amount"],
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
                "is_production": pref.get("is_production", mp.is_production),
                "order_id": order.id,
                "base_amount": breakdown["base_amount"],
                "fee_amount": breakdown["fee_amount"],
                "total_amount": breakdown["total_amount"],
                "fee_percentage": breakdown["fee_percentage"],
                "currency": breakdown["currency"],
            }
        )

    @action(detail=False, methods=["get"], url_path="my-orders")
    def my_orders(self, request):
        orders = PaymentOrder.objects.filter(user=request.user)[:20]
        return Response(PaymentOrderSerializer(orders, many=True).data)

    @action(detail=False, methods=["get"], url_path="my-purchases")
    def my_purchases(self, request):
        """
        Historial completo de compras del usuario autenticado.
        GET /api/v1/payments/my-purchases/
        Devuelve las órdenes ordenadas de la más reciente a la más antigua,
        con nombre de paquete, descripción, monto, estado y ID de MP.
        """
        orders = (
            PaymentOrder.objects.filter(user=request.user)
            .order_by("-created_at")
        )
        serializer = PurchaseHistorySerializer(orders, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="status")
    def payment_status(self, request):
        """
        Estado de una orden del usuario autenticado (polling post-checkout).
        GET /api/v1/payments/status/?order_id=&preference_id=&payment_id=
        """
        order_id = (
            request.query_params.get("order_id")
            or request.query_params.get("external_reference")
            or ""
        ).strip()
        preference_id = (request.query_params.get("preference_id") or "").strip()
        payment_id = (
            request.query_params.get("payment_id")
            or request.query_params.get("collection_id")
            or ""
        ).strip()

        qs = PaymentOrder.objects.filter(user=request.user)
        order = None
        if order_id:
            order = qs.filter(id=order_id).first()
        if order is None and preference_id:
            order = qs.filter(mp_preference_id=preference_id).first()
        if order is None and payment_id:
            order = qs.filter(mp_payment_id=payment_id).first()
        if order is None:
            return Response(
                {"detail": "Orden no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(PurchaseHistorySerializer(order).data)

    @action(
        detail=False,
        methods=["get"],
        url_path="billing",
        permission_classes=[IsAdminUser],
    )
    def billing(self, request):
        txs = TransaccionFacturacion.objects.select_related("user")[:100]
        return Response(TransaccionFacturacionSerializer(txs, many=True).data)

    @action(detail=False, methods=["get"], url_path="ledger")
    def ledger(self, request):
        """
        Historial global de pagos (tienda / deportes / eventos).
        GET /api/v1/payments/ledger/?category=tienda|deportes|eventos|all&export=csv
        """
        user = request.user
        if not (
            user_is_platform_elevated(user)
            or user_admin_level(user) >= 1
            or getattr(user, "is_staff", False)
        ):
            return Response(
                {"detail": "No tienes permiso para ver el historial global."},
                status=status.HTTP_403_FORBIDDEN,
            )

        from payments.ledger import build_payment_ledger, ledger_csv_response

        rows = build_payment_ledger(
            category=request.query_params.get("category") or "all",
            search=request.query_params.get("search") or "",
            date_from=request.query_params.get("date_from") or "",
            date_to=request.query_params.get("date_to") or "",
        )
        if (request.query_params.get("export") or "").lower() in ("csv", "excel"):
            return ledger_csv_response(rows)
        return Response({"count": len(rows), "results": rows})


@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def mercadopago_webhook(request):
    """
    Webhook de Mercado Pago (sandbox y producción).

    Flujo:
      1) Validar firma x-signature / x-request-id
      2) Persistir evento (auditoría)
      3) ACK 200 inmediato a Mercado Pago
      4) Procesar el pago en segundo plano (GET /v1/payments + acreditar)
    """
    sig = signature_from_request(request)
    data_id = sig["data_id"] or extract_data_id(request)
    x_signature = sig["x_signature"]
    x_request_id = sig["x_request_id"]

    topic = (
        request.query_params.get("topic")
        or request.query_params.get("type")
        or (request.data.get("type") if isinstance(request.data, dict) else "")
        or ""
    )
    action = request.data.get("action", "") if isinstance(request.data, dict) else ""

    signature_ok = verify_mercadopago_signature(
        x_signature=x_signature,
        x_request_id=x_request_id,
        data_id=str(data_id) if data_id else "",
    )
    if not signature_ok:
        # 401 para firmas inválidas; MP no debe reintentar con secreto incorrecto
        return Response({"detail": "invalid_signature"}, status=status.HTTP_401_UNAUTHORIZED)

    live_mode = None
    if isinstance(request.data, dict) and "live_mode" in request.data:
        live_mode = bool(request.data.get("live_mode"))

    event = MercadoPagoWebhookEvent.objects.create(
        topic=str(topic or ""),
        action=str(action or ""),
        resource_id=str(data_id or ""),
        request_id=str(x_request_id or ""),
        signature_valid=True,
        live_mode=live_mode,
        process_result="queued",
        payload={
            "query": dict(request.query_params),
            "body": request.data if isinstance(request.data, dict) else {},
            "headers": {
                "x-signature": x_signature,
                "x-request-id": x_request_id,
            },
        },
    )

    if not data_id:
        event.process_result = "no_payment_id"
        event.save(update_fields=["process_result"])
        return Response({"status": "no_payment_id"})

    is_payment = topic in ("payment", "payment.updated", "") or str(action).startswith("payment")
    if topic and topic not in ("payment",) and not str(action).startswith("payment"):
        event.process_result = "ignored_topic"
        event.save(update_fields=["process_result"])
        return Response({"status": "ignored", "topic": topic})

    if not is_payment and topic not in ("", "payment"):
        event.process_result = "ignored"
        event.save(update_fields=["process_result"])
        return Response({"status": "ignored"})

    dispatch_webhook_processing(event.id)
    return Response({"status": "received", "event_id": str(event.id)})


@api_view(["GET"])
@permission_classes([AllowAny])
def mp_public_config(request):
    """Expone la Public Key activa al frontend (seguro — nunca el access_token)."""
    cfg = get_mp_config()
    is_production = bool(cfg["is_production"])
    return Response(
        {
            "public_key": cfg["public_key"],
            "is_production": is_production,
            "environment": "production" if is_production else "sandbox",
        }
    )


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsAdminUser | IsSuperUser])
def mp_admin_config(request):
    """Gestión de credenciales Mercado Pago — IsAdminUser o IsSuperUser (Bearer)."""
    config = get_or_create_mp_config()

    if config is None:
        payload = dict(EMPTY_MP_ADMIN_CONFIG)
        if request.method == "PATCH":
            for key in payload:
                if key != "updated_at" and key in request.data:
                    payload[key] = request.data[key]
        return Response(payload, status=status.HTTP_200_OK)

    if request.method == "GET":
        serializer = MercadoPagoConfigSerializer(config)
        return Response(serializer.data, status=status.HTTP_200_OK)

    serializer = MercadoPagoConfigSerializer(config, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)
