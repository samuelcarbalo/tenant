from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from authentication.models import User
from core.models import TimeStampedModel
from organizations.models import Organization


class Category(TimeStampedModel):
    """Categoría de catálogo (tenant-scoped)."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="shop_categories",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        db_table = "ecommerce_categories"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"],
                name="uniq_ecommerce_category_org_slug",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "is_active", "sort_order"],
                name="ecommerce_c_organiz_7d1a0c_idx",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)


class Product(TimeStampedModel):
    """Producto del catálogo."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="shop_products",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(max_length=220)
    description = models.TextField(blank=True)
    short_description = models.CharField(max_length=300, blank=True)
    sku = models.CharField(max_length=64, blank=True, db_index=True)
    price_cop = models.DecimalField(max_digits=12, decimal_places=2)
    compare_at_price_cop = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    stock = models.PositiveIntegerField(default=0)
    image_url = models.URLField(blank=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_published = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "ecommerce_products"
        ordering = ["-is_featured", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"],
                name="uniq_ecommerce_product_org_slug",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "is_published", "is_active"],
                name="ecommerce_p_organiz_pub_idx",
            ),
            models.Index(
                fields=["organization", "category", "price_cop"],
                name="ecommerce_p_organiz_cat_idx",
            ),
            models.Index(fields=["name"], name="ecommerce_p_name_idx"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:200] or "producto"
            self.slug = base
        super().save(*args, **kwargs)


class Discount(TimeStampedModel):
    """Cupón / regla de descuento."""

    TYPE_PERCENT = "percent"
    TYPE_FIXED = "fixed"
    TYPE_CHOICES = [
        (TYPE_PERCENT, "Porcentaje"),
        (TYPE_FIXED, "Monto fijo COP"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="shop_discounts",
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    discount_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    min_order_cop = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    # Opcional: limitar a categoría
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discounts",
    )

    class Meta:
        db_table = "ecommerce_discounts"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uniq_ecommerce_discount_org_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "code", "is_active"],
                name="ecommerce_d_organiz_a1b2c3_idx",
            ),
        ]

    def __str__(self):
        return f"{self.code} ({self.discount_type})"

    def is_currently_valid(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False
        return True

    def compute_discount(self, subtotal: Decimal) -> Decimal:
        if subtotal < self.min_order_cop:
            return Decimal("0")
        if self.discount_type == self.TYPE_PERCENT:
            pct = min(self.value, Decimal("100"))
            return (subtotal * pct / Decimal("100")).quantize(Decimal("1"))
        return min(self.value, subtotal).quantize(Decimal("1"))


class ShopOrder(TimeStampedModel):
    """Pedido de tienda (pago en COP vía Mercado Pago)."""

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("approved", "Aprobado"),
        ("rejected", "Rechazado"),
        ("cancelled", "Cancelado"),
        ("refunded", "Reembolsado"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="shop_orders",
    )
    buyer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="shop_orders",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    subtotal_cop = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_cop = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_cop = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    discount = models.ForeignKey(
        Discount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    discount_code = models.CharField(max_length=40, blank=True)
    mp_preference_id = models.CharField(max_length=128, blank=True)
    mp_payment_id = models.CharField(max_length=64, blank=True, db_index=True)
    fulfilled = models.BooleanField(default=False, db_index=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "ecommerce_orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["buyer", "status", "created_at"],
                name="ecommerce_o_buyer_st_idx",
            ),
            models.Index(
                fields=["organization", "status"],
                name="ecommerce_o_organiz_st_idx",
            ),
        ]

    def __str__(self):
        return f"ShopOrder {self.id} ({self.status})"


class ShopOrderItem(models.Model):
    """Línea de pedido con snapshot de precio."""

    id = models.UUIDField(primary_key=True, editable=False)
    order = models.ForeignKey(
        ShopOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=64, blank=True)
    unit_price_cop = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(999)]
    )
    line_total_cop = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "ecommerce_order_items"

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"

    def save(self, *args, **kwargs):
        import uuid as _uuid

        if not self.id:
            self.id = _uuid.uuid4()
        super().save(*args, **kwargs)
