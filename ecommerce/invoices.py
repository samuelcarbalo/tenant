from django.db import IntegrityError, transaction
from django.utils import timezone

from payments.services.billing import calculate_billing_breakdown

from ecommerce.models import ShopInvoice, ShopOrder


def next_invoice_number() -> str:
    year = timezone.now().year
    prefix = f"CHV-{year}-"
    last = (
        ShopInvoice.objects.filter(number__startswith=prefix)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(str(last).split("-")[-1]) + 1
        except ValueError:
            seq = ShopInvoice.objects.filter(number__startswith=prefix).count() + 1
    return f"{prefix}{seq:06d}"


def sync_shop_invoice(order: ShopOrder) -> ShopInvoice:
    """Crea o actualiza la factura asociada al pedido."""
    buyer = order.buyer
    org = order.organization
    breakdown = calculate_billing_breakdown(order.total_cop)
    status = "issued" if order.status == "approved" else "pending"
    if order.status in ("rejected", "cancelled", "refunded"):
        status = "void"
    payload = {
        "seller_name": getattr(org, "name", None) or "Tienda Chever",
        "buyer_name": (getattr(buyer, "full_name", None) or "") or buyer.email,
        "buyer_email": buyer.email,
        "payment_method": "Mercado Pago",
        "subtotal_cop": order.subtotal_cop,
        "discount_cop": order.discount_cop,
        "total_cop": order.total_cop,
        "comision_mercado_pago": breakdown["comision_mercado_pago"],
        "iva_comision": breakdown["iva_comision"],
        "monto_neto_recibido": breakdown["monto_neto_recibido"],
        "status": status,
        "issued_at": timezone.now() if status == "issued" else None,
    }

    existing = ShopInvoice.objects.filter(order=order).first()
    if existing:
        for key, value in payload.items():
            if key == "issued_at" and existing.issued_at and status == "issued":
                continue
            setattr(existing, key, value)
        existing.save()
        return existing

    for _ in range(5):
        try:
            with transaction.atomic():
                return ShopInvoice.objects.create(
                    order=order,
                    number=next_invoice_number(),
                    **payload,
                )
        except IntegrityError:
            continue
    raise IntegrityError("No se pudo asignar número de factura.")
