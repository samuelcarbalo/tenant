"""
Procesamiento de webhooks Mercado Pago.

El endpoint HTTP responde 200 de inmediato; el trabajo pesado (GET /v1/payments,
acreditar créditos, cumplir pedidos de tienda) corre en un hilo daemon para no
bloquear el ACK hacia Mercado Pago.

En tests (`manage.py test` / pytest) el procesamiento es síncrono.
"""

from __future__ import annotations

import logging
import sys
import threading

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import close_old_connections

from notifications.services import notify_payment_status
from payments.models import MercadoPagoWebhookEvent, PaymentOrder
from payments.services.mercadopago_service import MercadoPagoService
from payments.services.payment_processor import apply_approved_payment

logger = logging.getLogger(__name__)


def webhook_processing_is_async() -> bool:
    if "test" in sys.argv or "pytest" in sys.modules:
        return False
    return bool(getattr(settings, "MP_WEBHOOK_ASYNC", True))


def dispatch_webhook_processing(event_id) -> None:
    """Encola el procesamiento sin bloquear la respuesta HTTP (salvo en tests)."""
    if not webhook_processing_is_async():
        process_webhook_event(event_id)
        return

    thread = threading.Thread(
        target=_process_webhook_event_safe,
        args=(str(event_id),),
        daemon=True,
        name=f"mp-webhook-{event_id}",
    )
    thread.start()


def _process_webhook_event_safe(event_id: str) -> None:
    close_old_connections()
    try:
        process_webhook_event(event_id)
    except Exception:
        logger.exception("Webhook MP: fallo asíncrono event=%s", event_id)
        try:
            MercadoPagoWebhookEvent.objects.filter(pk=event_id).update(
                process_result="async_error",
            )
        except Exception:
            logger.exception("Webhook MP: no se pudo marcar async_error event=%s", event_id)
    finally:
        close_old_connections()


def process_webhook_event(event_id) -> str:
    """
    Consulta el pago en Mercado Pago (sandbox o live según is_production)
    y aplica créditos / cumple el pedido de tienda. Idempotente.
    """
    try:
        event = MercadoPagoWebhookEvent.objects.get(pk=event_id)
    except MercadoPagoWebhookEvent.DoesNotExist:
        logger.warning("Webhook MP: evento inexistente %s", event_id)
        return "event_not_found"

    data_id = (event.resource_id or "").strip()
    if not data_id:
        event.process_result = "no_payment_id"
        event.save(update_fields=["process_result"])
        return "no_payment_id"

    try:
        mp = MercadoPagoService()
        payment = mp.get_payment(str(data_id))
    except Exception:
        logger.exception("Webhook: failed to fetch payment %s", data_id)
        event.process_result = "fetch_error"
        event.save(update_fields=["process_result"])
        return "fetch_error"

    payment_status = payment.get("status", "") or ""
    event.payment_status = str(payment_status)
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

                shop_order = ShopOrder.objects.select_related("buyer").get(id=external_ref)
            except Exception:
                logger.warning("Webhook: order not found %s", external_ref)
                event.process_result = "order_not_found"
                event.save(update_fields=["process_result"])
                return "order_not_found"

    if payment_status == "approved" and shop_order:
        from ecommerce.services import fulfill_shop_order

        applied = fulfill_shop_order(shop_order, str(data_id))
        event.processed_ok = True
        event.process_result = "shop_approved" if applied else "shop_already_applied"
        event.save(update_fields=["processed_ok", "process_result"])
        return event.process_result

    if payment_status == "approved" and order:
        applied = apply_approved_payment(order, str(data_id))
        event.processed_ok = True
        event.process_result = "approved" if applied else "already_applied"
        event.save(update_fields=["processed_ok", "process_result"])
        return event.process_result

    if shop_order and payment_status in ("rejected", "cancelled", "refunded"):
        from ecommerce.services import mark_shop_order_failed

        mark_shop_order_failed(shop_order, payment_status, str(data_id))
        event.processed_ok = True
        event.process_result = f"shop_{payment_status}"
        event.save(update_fields=["processed_ok", "process_result"])
        return event.process_result

    if order and payment_status:
        if payment_status in ("rejected", "cancelled", "refunded") and order.status != payment_status:
            order.status = (
                payment_status if payment_status in dict(PaymentOrder.STATUS_CHOICES) else "rejected"
            )
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
    return event.process_result
