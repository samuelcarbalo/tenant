import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from core.permissions import IsSuperUser, user_admin_level, user_is_platform_elevated
from notifications.services import notify_payment_status
from payments.models import MercadoPagoConfig, MercadoPagoWebhookEvent, PaymentOrder, TransaccionFacturacion
from payments.packages import CREDIT_PACKAGES, get_package
from payments.serializers import (
    CreatePreferenceSerializer,
    CreditPackageSerializer,
    MercadoPagoConfigSerializer,
    PaymentOrderSerializer,
    PurchaseHistorySerializer,
    TransaccionFacturacionSerializer,
)
from payments.services.mercadopago_service import MercadoPagoService
from payments.services.mp_config import (
    EMPTY_MP_ADMIN_CONFIG,
    get_mp_config,
    get_or_create_mp_config,
)
from payments.services.payment_processor import apply_approved_payment
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
                "is_production": pref.get("is_production", mp.is_production),
                "order_id": order.id,
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
    Webhook de Mercado Pago.

    Flujo:
      1) Validar firma x-signature / x-request-id
      2) Persistir evento (auditoría)
      3) Si topic/type = payment → GET /v1/payments/{id}
      4) Si approved → acreditar créditos + notificación in-app
      5) Responder 200 rápido (MP reintenta si falla)
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
        payload={
            "query": dict(request.query_params),
            "body": request.data if isinstance(request.data, dict) else {},
            "headers": {
                "x-signature": x_signature,
                "x-request-id": x_request_id,
            },
        },
    )

    # Solo procesamos pagos aquí; merchant_order se registra y se ignora con 200
    is_payment = topic in ("payment", "payment.updated", "") or str(action).startswith("payment")
    if not data_id:
        event.process_result = "no_payment_id"
        event.save(update_fields=["process_result"])
        return Response({"status": "no_payment_id"})

    if topic and topic not in ("payment",) and not str(action).startswith("payment"):
        event.process_result = "ignored_topic"
        event.save(update_fields=["process_result"])
        return Response({"status": "ignored", "topic": topic})

    if not is_payment and topic not in ("", "payment"):
        event.process_result = "ignored"
        event.save(update_fields=["process_result"])
        return Response({"status": "ignored"})

    try:
        mp = MercadoPagoService()
        payment = mp.get_payment(str(data_id))
    except Exception:
        logger.exception("Webhook: failed to fetch payment %s", data_id)
        event.process_result = "fetch_error"
        event.save(update_fields=["process_result"])
        # 200 para evitar storm de reintentos ante fallos temporales de red
        return Response({"status": "error_fetching_payment"})

    payment_status = payment.get("status", "")
    event.payment_status = str(payment_status or "")
    event.save(update_fields=["payment_status"])

    external_ref = payment.get("external_reference")
    order = None
    shop_order = None
    if external_ref:
        try:
            order = PaymentOrder.objects.select_related("user").get(id=external_ref)
            event.payment_order = order
            event.save(update_fields=["payment_order"])
        except (PaymentOrder.DoesNotExist, ValueError, ValidationError):
            try:
                from ecommerce.models import ShopOrder
                from ecommerce.services import fulfill_shop_order, mark_shop_order_failed

                shop_order = ShopOrder.objects.select_related("buyer").get(id=external_ref)
            except Exception:
                logger.warning("Webhook: order not found %s", external_ref)
                event.process_result = "order_not_found"
                event.save(update_fields=["process_result"])
                return Response({"status": "order_not_found"})

    if payment_status == "approved" and shop_order:
        from ecommerce.services import fulfill_shop_order

        applied = fulfill_shop_order(shop_order, str(data_id))
        event.processed_ok = True
        event.process_result = "shop_approved" if applied else "shop_already_applied"
        event.save(update_fields=["processed_ok", "process_result"])
        return Response({"status": event.process_result})

    if payment_status == "approved" and order:
        applied = apply_approved_payment(order, str(data_id))
        event.processed_ok = True
        event.process_result = "approved" if applied else "already_applied"
        event.save(update_fields=["processed_ok", "process_result"])
        return Response({"status": event.process_result})

    if shop_order and payment_status in ("rejected", "cancelled", "refunded"):
        from ecommerce.services import mark_shop_order_failed

        mark_shop_order_failed(shop_order, payment_status, str(data_id))
        event.processed_ok = True
        event.process_result = f"shop_{payment_status}"
        event.save(update_fields=["processed_ok", "process_result"])
        return Response({"status": event.process_result})

    # Estados no aprobados → actualizar orden + avisar al usuario (sin duplicar spam)
    if order and payment_status:
        if payment_status in ("rejected", "cancelled", "refunded") and order.status != payment_status:
            order.status = payment_status if payment_status in dict(PaymentOrder.STATUS_CHOICES) else "rejected"
            order.mp_payment_id = str(data_id)
            order.save(update_fields=["status", "mp_payment_id", "updated_at"])
            try:
                notify_payment_status(
                    user=order.user,
                    status=payment_status,
                    order_id=str(order.id),
                    mp_payment_id=str(data_id),
                    amount_cop=order.amount_cop,
                    credits=order.credits_amount,
                )
            except Exception:
                logger.exception("notify_payment_status failed for order=%s", order.id)
        elif payment_status in ("pending", "in_process") and order.status == "pending":
            # Una sola notificación pending por orden (evitar spam de webhooks)
            from notifications.models import Notification, NotificationType

            already = Notification.objects.filter(
                user=order.user,
                type=NotificationType.PAYMENT_PENDING,
                extra_data__order_id=str(order.id),
            ).exists()
            if not already:
                try:
                    notify_payment_status(
                        user=order.user,
                        status=payment_status,
                        order_id=str(order.id),
                        mp_payment_id=str(data_id),
                        amount_cop=order.amount_cop,
                        credits=order.credits_amount,
                    )
                except Exception:
                    logger.exception("notify pending failed order=%s", order.id)

    event.processed_ok = True
    event.process_result = payment_status or "unknown"
    event.save(update_fields=["processed_ok", "process_result"])
    return Response({"status": payment_status or "unknown"})


@api_view(["GET"])
@permission_classes([AllowAny])
def mp_public_config(request):
    """Expone la Public Key activa al frontend (seguro — es pública)."""
    cfg = get_mp_config()
    return Response(
        {
            "public_key": cfg["public_key"],
            "is_production": cfg["is_production"],
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
