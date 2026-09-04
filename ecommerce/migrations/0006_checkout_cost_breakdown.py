from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ecommerce", "0005_product_created_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoporder",
            name="shipping_cop",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0"), max_digits=12
            ),
        ),
        migrations.AddField(
            model_name="shoporder",
            name="payment_fee_cop",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0"), max_digits=12
            ),
        ),
        migrations.AddField(
            model_name="shoporder",
            name="fee_percentage",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="storesettings",
            name="shipping_cost_cop",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Costo de envío trasladado al comprador en checkout (0 = no aplica).",
                max_digits=12,
            ),
        ),
    ]
