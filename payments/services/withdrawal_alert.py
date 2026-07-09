import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from payments.models import TransaccionFacturacion, WithdrawalAlert

logger = logging.getLogger(__name__)


def check_withdrawal_alert() -> WithdrawalAlert | None:
    """
    Genera alerta si hay fondos acumulados sin retiro y se acerca el límite de 180 días
    de Mercado Pago. Ejecutar vía cron diario o management command.
    """
    alert_days = getattr(settings, "MP_WITHDRAWAL_ALERT_DAYS", 150)
    max_days = getattr(settings, "MP_WITHDRAWAL_MAX_DAYS", 180)

    unresolved = WithdrawalAlert.objects.filter(is_resolved=False).first()
    if unresolved:
        return unresolved

    last_tx = TransaccionFacturacion.objects.order_by("-created_at").first()
    if not last_tx:
        return None

    days_since = (timezone.now() - last_tx.created_at).days
    if days_since < alert_days:
        return None

    total_pending = sum(
        t.monto_neto_recibido for t in TransaccionFacturacion.objects.all()
    )

    message = (
        f"ALERTA DE RETIRO ACH: Han transcurrido {days_since} días desde la última "
        f"transacción registrada. Mercado Pago recomienda retirar fondos antes de "
        f"{max_days} días para evitar inactividad. "
        f"Monto neto acumulado estimado: ${total_pending:,.0f} COP. "
        f"Realice transferencia ACH a la cuenta bancaria tradicional."
    )

    alert = WithdrawalAlert.objects.create(
        message=message,
        total_pending_cop=total_pending,
        days_since_last_withdrawal=days_since,
    )
    logger.warning("Withdrawal alert created: %s", alert.id)
    return alert
