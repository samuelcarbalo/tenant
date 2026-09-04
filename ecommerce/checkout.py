"""Cálculo de totales de checkout y armado de ítems de preferencia MP."""

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from ecommerce.models import ShopOrder, StoreSettings
from payments.services.billing import buyer_processing_surcharge


def cop_amount(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def cop_int(value) -> int:
    return int(cop_amount(value))


def resolve_shipping_cost(organization) -> Decimal:
    if organization is not None:
        stored = (
            StoreSettings.objects.filter(organization=organization)
            .values_list("shipping_cost_cop", flat=True)
            .first()
        )
        if stored is not None:
            return cop_amount(stored)
    return cop_amount(getattr(settings, "SHOP_SHIPPING_COST_COP", 0) or 0)


def compute_checkout_totals(
    *,
    subtotal: Decimal | int | float,
    discount_amount: Decimal | int | float = 0,
    shipping_cost: Decimal | int | float = 0,
) -> dict:
    subtotal_cop = cop_amount(subtotal)
    discount_cop = cop_amount(discount_amount)
    shipping_cop = cop_amount(shipping_cost)
    products_net = max(subtotal_cop - discount_cop, Decimal("0"))
    surcharge = buyer_processing_surcharge(products_net + shipping_cop)
    return {
        "subtotal": subtotal_cop,
        "discount": discount_cop,
        "shipping_cost": shipping_cop,
        "payment_fee": surcharge["payment_fee"],
        "fee_percentage": surcharge["fee_percentage"],
        "total_amount": surcharge["charged_total"],
        "currency": "COP",
    }


def checkout_public_payload(totals: dict) -> dict:
    return {
        "subtotal": cop_int(totals["subtotal"]),
        "discount": cop_int(totals["discount"]),
        "payment_fee": cop_int(totals["payment_fee"]),
        "fee_percentage": totals["fee_percentage"],
        "shipping_cost": cop_int(totals["shipping_cost"]),
        "total_amount": cop_int(totals["total_amount"]),
        "currency": totals.get("currency") or "COP",
    }


def checkout_payload_from_order(order: ShopOrder) -> dict:
    return checkout_public_payload(
        {
            "subtotal": order.subtotal_cop,
            "discount": order.discount_cop,
            "shipping_cost": order.shipping_cop,
            "payment_fee": order.payment_fee_cop,
            "fee_percentage": order.fee_percentage or buyer_processing_surcharge(0)["fee_percentage"],
            "total_amount": order.total_cop,
            "currency": "COP",
        }
    )


def build_mp_preference_items(order: ShopOrder) -> list[dict]:
    """Ítems enviados a Mercado Pago, alineados 1:1 con el desglose de checkout."""
    product_items = list(order.items.all())
    items: list[dict] = []

    if order.discount_cop and order.discount_cop > 0:
        items.append(
            {
                "id": f"{order.id}-products",
                "title": f"Pedido tienda ({len(product_items)} ítems)"[:120],
                "description": f"Descuento {order.discount_code or ''}".strip(),
                "quantity": 1,
                "currency_id": "COP",
                "unit_price": float(cop_amount(order.subtotal_cop - order.discount_cop)),
            }
        )
    else:
        for item in product_items:
            items.append(
                {
                    "id": str(item.product_id or item.id),
                    "title": item.product_name[:120],
                    "description": item.product_sku or item.product_name,
                    "quantity": item.quantity,
                    "currency_id": "COP",
                    "unit_price": float(cop_amount(item.unit_price_cop)),
                }
            )

    if order.shipping_cop and order.shipping_cop > 0:
        items.append(
            {
                "id": f"{order.id}-shipping",
                "title": "Costo de Envío",
                "description": "Costo de envío / comisión de entrega",
                "quantity": 1,
                "currency_id": "COP",
                "unit_price": float(cop_amount(order.shipping_cop)),
            }
        )

    if order.payment_fee_cop and order.payment_fee_cop > 0:
        items.append(
            {
                "id": f"{order.id}-fee",
                "title": "Comisión por Procesamiento de Pago",
                "description": "Tarifa de procesamiento Mercado Pago",
                "quantity": 1,
                "currency_id": "COP",
                "unit_price": float(cop_amount(order.payment_fee_cop)),
            }
        )

    return items
