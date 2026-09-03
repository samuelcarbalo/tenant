from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.db.models import F

from ecommerce.models import Discount, Product, ShopOrder, ShopOrderItem

CACHE_TTL_CATEGORIES = 300
CACHE_TTL_PRODUCT_DETAIL = 120


def categories_cache_key(org_id: str) -> str:
    return f"ecommerce:categories:{org_id}"


def product_detail_cache_key(org_id: str, slug: str) -> str:
    return f"ecommerce:product:{org_id}:{slug}"


def invalidate_catalog_cache(org_id: str, slug: str | None = None) -> None:
    cache.delete(categories_cache_key(str(org_id)))
    if slug:
        cache.delete(product_detail_cache_key(str(org_id), slug))


def resolve_discount(*, organization, code: str | None) -> Discount | None:
    if not code:
        return None
    discount = (
        Discount.objects.filter(
            organization=organization,
            code__iexact=code.strip(),
            is_active=True,
        )
        .select_related("category")
        .first()
    )
    if not discount or not discount.is_currently_valid():
        return None
    return discount


@transaction.atomic
def create_shop_order(
    *,
    buyer,
    organization,
    items: list[dict],
    discount_code: str | None = None,
) -> ShopOrder:
    """
    Crea pedido + líneas. items = [{product_id, quantity}, ...]
    Reserva stock de forma optimista (F expressions).
    """
    if not items:
        raise ValueError("El carrito está vacío.")

    product_ids = [str(i["product_id"]) for i in items]
    products = {
        str(p.id): p
        for p in Product.objects.select_for_update()
        .filter(
            id__in=product_ids,
            organization=organization,
            is_published=True,
            is_active=True,
        )
        .select_related("category")
    }
    if len(products) != len(set(product_ids)):
        raise ValueError("Uno o más productos no están disponibles.")

    lines: list[tuple[Product, int, Decimal]] = []
    subtotal = Decimal("0")
    for raw in items:
        product = products[str(raw["product_id"])]
        qty = int(raw["quantity"])
        if qty < 1:
            raise ValueError("Cantidad inválida.")
        if product.stock < qty:
            raise ValueError(f"Stock insuficiente para {product.name}.")
        line_total = (product.price_cop * qty).quantize(Decimal("1"))
        lines.append((product, qty, line_total))
        subtotal += line_total

    discount = resolve_discount(organization=organization, code=discount_code)
    discount_amount = discount.compute_discount(subtotal) if discount else Decimal("0")
    total = max(subtotal - discount_amount, Decimal("0"))

    order = ShopOrder.objects.create(
        organization=organization,
        buyer=buyer,
        subtotal_cop=subtotal,
        discount_cop=discount_amount,
        total_cop=total,
        discount=discount,
        discount_code=(discount.code if discount else ""),
    )

    for product, qty, line_total in lines:
        ShopOrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            product_sku=product.sku,
            unit_price_cop=product.price_cop,
            quantity=qty,
            line_total_cop=line_total,
        )
        updated = Product.objects.filter(pk=product.pk, stock__gte=qty).update(
            stock=F("stock") - qty
        )
        if not updated:
            raise ValueError(f"Stock insuficiente para {product.name}.")

    from ecommerce.invoices import sync_shop_invoice

    sync_shop_invoice(order)
    return order


@transaction.atomic
def fulfill_shop_order(order: ShopOrder, mp_payment_id: str) -> bool:
    """Marca pedido como pagado (idempotente)."""
    locked = ShopOrder.objects.select_for_update().get(pk=order.pk)
    if locked.fulfilled and locked.status == "approved":
        return False

    locked.status = "approved"
    locked.mp_payment_id = str(mp_payment_id)
    locked.fulfilled = True
    locked.save(update_fields=["status", "mp_payment_id", "fulfilled", "updated_at"])

    from ecommerce.invoices import sync_shop_invoice

    sync_shop_invoice(locked)

    if locked.discount_id:
        Discount.objects.filter(pk=locked.discount_id).update(used_count=F("used_count") + 1)

    return True


@transaction.atomic
def mark_shop_order_failed(order: ShopOrder, status: str, mp_payment_id: str) -> None:
    locked = ShopOrder.objects.select_for_update().get(pk=order.pk)
    if locked.fulfilled:
        return
    if locked.status == status:
        return
    # Liberar stock reservado al cancelar/rechazar
    if locked.status == "pending" and status in ("rejected", "cancelled", "refunded"):
        for item in locked.items.select_related("product"):
            if item.product_id:
                Product.objects.filter(pk=item.product_id).update(
                    stock=F("stock") + item.quantity
                )
    locked.status = status if status in dict(ShopOrder.STATUS_CHOICES) else "rejected"
    locked.mp_payment_id = str(mp_payment_id)
    locked.save(update_fields=["status", "mp_payment_id", "updated_at"])
    from ecommerce.invoices import sync_shop_invoice

    sync_shop_invoice(locked)
