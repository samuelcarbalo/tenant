from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings


def mp_commission_rate() -> Decimal:
    return Decimal(str(getattr(settings, "MP_COMMISSION_RATE", 0.0329)))


def mp_iva_rate() -> Decimal:
    return Decimal(str(getattr(settings, "MP_IVA_RATE", 0.19)))


def effective_mp_fee_rate() -> Decimal:
    """Tasa efectiva cobrada al comprador: comisión MP + IVA sobre esa comisión."""
    return mp_commission_rate() * (Decimal("1") + mp_iva_rate())


def format_fee_percentage() -> str:
    pct = (effective_mp_fee_rate() * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"{pct}%"


def calculate_billing_breakdown(monto_total: Decimal | int | float) -> dict:
    """
    Calcula comisión MP (3.29%), IVA sobre comisión (19%) y neto recibido.
    """
    total = Decimal(str(monto_total))
    commission_rate = mp_commission_rate()
    iva_rate = mp_iva_rate()

    comision = (total * commission_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    iva = (comision * iva_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    neto = (total - comision - iva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "monto_total": total,
        "comision_mercado_pago": comision,
        "iva_comision": iva,
        "monto_neto_recibido": neto,
    }


def buyer_processing_surcharge(base_amount: Decimal | int | float) -> dict:
    """
    Recargo trasladado al comprador para que, tras comisión MP + IVA,
    el vendedor reciba aproximadamente ``base_amount``.

    T * (1 - c * (1 + iva)) = B  =>  T = B / (1 - tasa_efectiva)
    payment_fee = T - B
    """
    base = Decimal(str(base_amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    percentage = format_fee_percentage()
    if base <= 0:
        return {
            "payment_fee": Decimal("0"),
            "fee_percentage": percentage,
            "charged_total": Decimal("0"),
        }

    rate = effective_mp_fee_rate()
    denominator = Decimal("1") - rate
    if denominator <= 0:
        charged = base
    else:
        charged = (base / denominator).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    fee = max(charged - base, Decimal("0"))
    return {
        "payment_fee": fee,
        "fee_percentage": percentage,
        "charged_total": base + fee,
    }
