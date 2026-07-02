from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings


def calculate_billing_breakdown(monto_total: Decimal | int | float) -> dict:
    """
    Calcula comisión MP (3.29%), IVA sobre comisión (19%) y neto recibido.
    """
    total = Decimal(str(monto_total))
    commission_rate = Decimal(str(getattr(settings, "MP_COMMISSION_RATE", 0.0329)))
    iva_rate = Decimal(str(getattr(settings, "MP_IVA_RATE", 0.19)))

    comision = (total * commission_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    iva = (comision * iva_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    neto = (total - comision - iva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "monto_total": total,
        "comision_mercado_pago": comision,
        "iva_comision": iva,
        "monto_neto_recibido": neto,
    }
