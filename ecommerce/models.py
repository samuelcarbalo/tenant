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


class SubCategory(TimeStampedModel):
    """Subcategoría de catálogo (pertenece a una Category)."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="shop_subcategories",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="subcategories",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        db_table = "ecommerce_subcategories"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"],
                name="uniq_ecommerce_subcategory_org_slug",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "category", "is_active", "sort_order"],
                name="ecommerce_sc_org_cat_idx",
            ),
        ]

    def __str__(self):
        return f"{self.category.name} / {self.name}"

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
    subcategory = models.ForeignKey(
        "SubCategory",
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
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shop_products_created",
    )

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


class ProductDiscount(TimeStampedModel):
    """
    Oferta / flash sale aplicada a uno o más productos (por SKU o ID).
    Independiente del cupón `Discount` de checkout.
    """

    TYPE_PERCENT = "percent"
    TYPE_FIXED = "fixed"
    TYPE_PRICE = "price"  # precio final fijo (discount_price)
    TYPE_CHOICES = [
        (TYPE_PERCENT, "Porcentaje"),
        (TYPE_FIXED, "Monto fijo COP"),
        (TYPE_PRICE, "Precio promocional"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="product_discounts",
    )
    name = models.CharField(max_length=160)
    discount_type = models.CharField(
        max_length=16, choices=TYPE_CHOICES, default=TYPE_PERCENT
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    discount_amount_cop = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    discount_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Precio final COP cuando discount_type=price",
    )
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)
    is_flash_sale = models.BooleanField(default=True)
    products = models.ManyToManyField(
        Product,
        related_name="product_discounts",
        blank=True,
    )

    class Meta:
        db_table = "ecommerce_product_discounts"
        ordering = ["-start_time"]
        indexes = [
            models.Index(
                fields=["organization", "is_active", "start_time", "end_time"],
                name="ecommerce_pd_org_active_idx",
            ),
        ]

    def __str__(self):
        return self.name

    def is_currently_valid(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        return self.start_time <= now <= self.end_time

    def apply_to_price(self, base_price: Decimal) -> Decimal:
        if self.discount_type == self.TYPE_PERCENT and self.discount_percentage is not None:
            pct = min(self.discount_percentage, Decimal("100"))
            return (base_price * (Decimal("100") - pct) / Decimal("100")).quantize(
                Decimal("1")
            )
        if self.discount_type == self.TYPE_FIXED and self.discount_amount_cop is not None:
            return max(base_price - self.discount_amount_cop, Decimal("0")).quantize(
                Decimal("1")
            )
        if self.discount_type == self.TYPE_PRICE and self.discount_price is not None:
            return min(self.discount_price, base_price).quantize(Decimal("1"))
        return base_price


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
    shipping_cop = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    payment_fee_cop = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    fee_percentage = models.CharField(max_length=16, blank=True)
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
    DELIVERY_CHOICES = [
        ("pending", "Pendiente"),
        ("processing", "En preparación"),
        ("shipped", "Enviado"),
        ("delivered", "Entregado"),
        ("cancelled", "Cancelado"),
    ]
    delivery_status = models.CharField(
        max_length=20,
        choices=DELIVERY_CHOICES,
        default="pending",
        db_index=True,
    )

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


class ShopInvoice(TimeStampedModel):
    """Factura de compra de tienda (emisor = organización, receptor = comprador)."""

    STATUS_CHOICES = [
        ("pending", "Pendiente de pago"),
        ("issued", "Pagada"),
        ("void", "Anulada"),
    ]

    order = models.OneToOneField(
        ShopOrder,
        on_delete=models.CASCADE,
        related_name="invoice",
    )
    number = models.CharField(max_length=32, unique=True, db_index=True)
    seller_name = models.CharField(max_length=255)
    buyer_name = models.CharField(max_length=255)
    buyer_email = models.EmailField()
    payment_method = models.CharField(max_length=64, default="Mercado Pago")
    subtotal_cop = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_cop = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_cop = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    comision_mercado_pago = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    iva_comision = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    monto_neto_recibido = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ecommerce_invoices"
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class StoreSettings(TimeStampedModel):
    """Configuración visual de la tienda (un registro por organización)."""

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="store_settings",
    )
    store_logo = models.URLField(blank=True, max_length=500)
    shipping_cost_cop = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Costo de envío trasladado al comprador en checkout (0 = no aplica).",
    )

    class Meta:
        db_table = "ecommerce_store_settings"
        verbose_name = "Configuración de tienda"
        verbose_name_plural = "Configuraciones de tienda"

    def __str__(self):
        return f"Store settings ({self.organization_id})"
