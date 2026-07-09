import logging

from django.db import transaction
from django.db.models import F

from authentication.models import User
from payments.models import PaymentOrder, TransaccionFacturacion
from payments.packages import get_package
from payments.services.billing import calculate_billing_breakdown
from payments.services.withdrawal_alert import check_withdrawal_alert

logger = logging.getLogger(__name__)


def apply_approved_payment(payment_order: PaymentOrder, mp_payment_id: str) -> bool:
    """
    Acredita créditos al usuario de forma idempotente.
    Retorna True si se aplicaron créditos, False si ya estaban aplicados.
    """
    if payment_order.credits_applied:
        logger.info("Payment order %s already applied", payment_order.id)
        return False

    package = get_package(payment_order.package_id)
    if not package:
        logger.error("Invalid package on order %s", payment_order.id)
        return False

    with transaction.atomic():
        order = PaymentOrder.objects.select_for_update().get(pk=payment_order.pk)
        if order.credits_applied:
            return False

        user = User.objects.select_for_update().get(pk=order.user_id)
        user.credits = F("credits") + order.credits_amount
        user.save(update_fields=["credits"])
        user.refresh_from_db()

        billing = calculate_billing_breakdown(order.amount_cop)
        TransaccionFacturacion.objects.create(
            payment_order=order,
            user=user,
            monto_total=billing["monto_total"],
            comision_mercado_pago=billing["comision_mercado_pago"],
            iva_comision=billing["iva_comision"],
            monto_neto_recibido=billing["monto_neto_recibido"],
            creditos_comprados=order.credits_amount,
            mp_payment_id=mp_payment_id,
            package_id=order.package_id,
        )

        order.status = "approved"
        order.mp_payment_id = mp_payment_id
        order.credits_applied = True
        order.save(update_fields=["status", "mp_payment_id", "credits_applied", "updated_at"])

    check_withdrawal_alert()
    logger.info(
        "Credits applied: user=%s credits=+%s order=%s",
        user.id,
        order.credits_amount,
        order.id,
    )
    return True
