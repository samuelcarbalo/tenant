import uuid
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=140)),
                ("description", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(db_index=True, default=0)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shop_categories",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "db_table": "ecommerce_categories",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="Discount",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("code", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=120)),
                (
                    "discount_type",
                    models.CharField(
                        choices=[("percent", "Porcentaje"), ("fixed", "Monto fijo COP")],
                        max_length=16,
                    ),
                ),
                (
                    "value",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                    ),
                ),
                ("min_order_cop", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12)),
                ("max_uses", models.PositiveIntegerField(blank=True, null=True)),
                ("used_count", models.PositiveIntegerField(default=0)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="discounts",
                        to="ecommerce.category",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shop_discounts",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "db_table": "ecommerce_discounts",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("name", models.CharField(db_index=True, max_length=200)),
                ("slug", models.SlugField(max_length=220)),
                ("description", models.TextField(blank=True)),
                ("short_description", models.CharField(blank=True, max_length=300)),
                ("sku", models.CharField(blank=True, db_index=True, max_length=64)),
                ("price_cop", models.DecimalField(decimal_places=2, max_digits=12)),
                ("compare_at_price_cop", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("stock", models.PositiveIntegerField(default=0)),
                ("image_url", models.URLField(blank=True)),
                ("is_featured", models.BooleanField(db_index=True, default=False)),
                ("is_published", models.BooleanField(db_index=True, default=True)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="products",
                        to="ecommerce.category",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shop_products",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "db_table": "ecommerce_products",
                "ordering": ["-is_featured", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ShopOrder",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendiente"),
                            ("approved", "Aprobado"),
                            ("rejected", "Rechazado"),
                            ("cancelled", "Cancelado"),
                            ("refunded", "Reembolsado"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("subtotal_cop", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12)),
                ("discount_cop", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12)),
                ("total_cop", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12)),
                ("discount_code", models.CharField(blank=True, max_length=40)),
                ("mp_preference_id", models.CharField(blank=True, max_length=128)),
                ("mp_payment_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("fulfilled", models.BooleanField(db_index=True, default=False)),
                ("notes", models.CharField(blank=True, max_length=255)),
                (
                    "buyer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shop_orders",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "discount",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="orders",
                        to="ecommerce.discount",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shop_orders",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "db_table": "ecommerce_orders",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ShopOrderItem",
            fields=[
                ("id", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("product_name", models.CharField(max_length=200)),
                ("product_sku", models.CharField(blank=True, max_length=64)),
                ("unit_price_cop", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "quantity",
                    models.PositiveIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(999),
                        ]
                    ),
                ),
                ("line_total_cop", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="ecommerce.shoporder",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="order_items",
                        to="ecommerce.product",
                    ),
                ),
            ],
            options={
                "db_table": "ecommerce_order_items",
            },
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                fields=("organization", "slug"), name="uniq_ecommerce_category_org_slug"
            ),
        ),
        migrations.AddIndex(
            model_name="category",
            index=models.Index(fields=["organization", "is_active", "sort_order"], name="ecommerce_c_organiz_7d1a0c_idx"),
        ),
        migrations.AddConstraint(
            model_name="discount",
            constraint=models.UniqueConstraint(
                fields=("organization", "code"), name="uniq_ecommerce_discount_org_code"
            ),
        ),
        migrations.AddIndex(
            model_name="discount",
            index=models.Index(fields=["organization", "code", "is_active"], name="ecommerce_d_organiz_a1b2c3_idx"),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(
                fields=("organization", "slug"), name="uniq_ecommerce_product_org_slug"
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["organization", "is_published", "is_active"], name="ecommerce_p_organiz_pub_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["organization", "category", "price_cop"], name="ecommerce_p_organiz_cat_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["name"], name="ecommerce_p_name_idx"),
        ),
        migrations.AddIndex(
            model_name="shoporder",
            index=models.Index(fields=["buyer", "status", "created_at"], name="ecommerce_o_buyer_st_idx"),
        ),
        migrations.AddIndex(
            model_name="shoporder",
            index=models.Index(fields=["organization", "status"], name="ecommerce_o_organiz_st_idx"),
        ),
    ]
