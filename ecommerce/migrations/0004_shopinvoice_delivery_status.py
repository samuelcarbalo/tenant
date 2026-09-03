from decimal import Decimal
import uuid

from django.db import migrations, models


def backfill_invoices(apps, schema_editor):
    ShopOrder = apps.get_model("ecommerce", "ShopOrder")
    ShopInvoice = apps.get_model("ecommerce", "ShopInvoice")
    rate = Decimal("0.0329")
    iva_rate = Decimal("0.19")
    year_counters = {}
    for order in ShopOrder.objects.select_related("buyer", "organization").order_by("created_at"):
        if ShopInvoice.objects.filter(order_id=order.id).exists():
            continue
        year = order.created_at.year if order.created_at else 2026
        year_counters[year] = year_counters.get(year, 0) + 1
        total = Decimal(str(order.total_cop or 0))
        commission = (total * rate).quantize(Decimal("0.01"))
        iva = (commission * iva_rate).quantize(Decimal("0.01"))
        neto = (total - commission - iva).quantize(Decimal("0.01"))
        buyer = order.buyer
        org = order.organization
        name = ""
        if buyer:
            name = f"{getattr(buyer, 'first_name', '')} {getattr(buyer, 'last_name', '')}".strip()
        status = "issued" if order.status == "approved" else "pending"
        if order.status in ("rejected", "cancelled", "refunded"):
            status = "void"
        ShopInvoice.objects.create(
            order_id=order.id,
            number=f"CHV-{year}-{year_counters[year]:06d}",
            seller_name=getattr(org, "name", None) or "Tienda Chever",
            buyer_name=name or (buyer.email if buyer else ""),
            buyer_email=buyer.email if buyer else "unknown@chever.co",
            payment_method="Mercado Pago",
            subtotal_cop=order.subtotal_cop,
            discount_cop=order.discount_cop,
            total_cop=order.total_cop,
            comision_mercado_pago=commission,
            iva_comision=iva,
            monto_neto_recibido=neto,
            status=status,
            issued_at=order.created_at if status == "issued" else None,
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ecommerce", "0003_storesettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoporder",
            name="delivery_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pendiente"),
                    ("processing", "En preparación"),
                    ("shipped", "Enviado"),
                    ("delivered", "Entregado"),
                    ("cancelled", "Cancelado"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="ShopInvoice",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("number", models.CharField(db_index=True, max_length=32, unique=True)),
                ("seller_name", models.CharField(max_length=255)),
                ("buyer_name", models.CharField(max_length=255)),
                ("buyer_email", models.EmailField(max_length=254)),
                ("payment_method", models.CharField(default="Mercado Pago", max_length=64)),
                (
                    "subtotal_cop",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "discount_cop",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "total_cop",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "comision_mercado_pago",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "iva_comision",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "monto_neto_recibido",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendiente de pago"),
                            ("issued", "Pagada"),
                            ("void", "Anulada"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=models.CASCADE,
                        related_name="invoice",
                        to="ecommerce.shoporder",
                    ),
                ),
            ],
            options={
                "db_table": "ecommerce_invoices",
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunPython(backfill_invoices, noop),
    ]
