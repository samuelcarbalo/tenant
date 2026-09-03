from django.utils import timezone
from rest_framework import serializers

from ecommerce.models import (
    Category,
    Discount,
    Product,
    ProductDiscount,
    ShopInvoice,
    ShopOrder,
    ShopOrderItem,
    SubCategory,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "sort_order",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at"]


class SubCategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = SubCategory
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "sort_order",
            "category",
            "category_name",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at"]


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    category_slug = serializers.SerializerMethodField()
    subcategory_name = serializers.SerializerMethodField()
    subcategory_slug = serializers.SerializerMethodField()
    active_discount = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "short_description",
            "sku",
            "price_cop",
            "compare_at_price_cop",
            "stock",
            "image_url",
            "is_featured",
            "category",
            "category_name",
            "category_slug",
            "subcategory",
            "subcategory_name",
            "subcategory_slug",
            "active_discount",
            "created_at",
        ]

    def get_category_name(self, obj):
        category = getattr(obj, "category", None)
        return getattr(category, "name", None) if category is not None else None

    def get_category_slug(self, obj):
        category = getattr(obj, "category", None)
        return getattr(category, "slug", None) if category is not None else None

    def get_subcategory_name(self, obj):
        sub = getattr(obj, "subcategory", None)
        return getattr(sub, "name", None) if sub is not None else None

    def get_subcategory_slug(self, obj):
        sub = getattr(obj, "subcategory", None)
        return getattr(sub, "slug", None) if sub is not None else None

    def get_active_discount(self, obj):
        now = timezone.now()
        qs = getattr(obj, "product_discounts", None)
        if qs is None:
            return None
        discount = (
            qs.filter(is_active=True, start_time__lte=now, end_time__gte=now)
            .order_by("-start_time")
            .first()
        )
        if not discount:
            return None
        return {
            "id": str(discount.id),
            "name": discount.name,
            "discount_type": discount.discount_type,
            "discount_percentage": (
                str(discount.discount_percentage)
                if discount.discount_percentage is not None
                else None
            ),
            "discount_price": (
                str(discount.discount_price) if discount.discount_price is not None else None
            ),
            "start_time": discount.start_time.isoformat(),
            "end_time": discount.end_time.isoformat(),
            "is_flash_sale": discount.is_flash_sale,
        }


class ProductDetailSerializer(ProductListSerializer):
    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ["description", "is_published", "updated_at"]


class ProductWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "description",
            "short_description",
            "sku",
            "price_cop",
            "compare_at_price_cop",
            "stock",
            "image_url",
            "is_featured",
            "is_published",
            "category",
            "subcategory",
            "is_active",
        ]
        extra_kwargs = {"slug": {"required": False, "allow_blank": True}}


class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = [
            "id",
            "code",
            "name",
            "discount_type",
            "value",
            "min_order_cop",
            "max_uses",
            "used_count",
            "starts_at",
            "ends_at",
            "category",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "used_count", "created_at"]


class CartItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=99)


class CheckoutSerializer(serializers.Serializer):
    items = CartItemSerializer(many=True)
    discount_code = serializers.CharField(required=False, allow_blank=True, max_length=40)


class ShopOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopOrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "unit_price_cop",
            "quantity",
            "line_total_cop",
        ]


class ShopInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopInvoice
        fields = [
            "id",
            "number",
            "seller_name",
            "buyer_name",
            "buyer_email",
            "payment_method",
            "subtotal_cop",
            "discount_cop",
            "total_cop",
            "comision_mercado_pago",
            "iva_comision",
            "monto_neto_recibido",
            "status",
            "issued_at",
            "created_at",
        ]


class ShopOrderSerializer(serializers.ModelSerializer):
    items = ShopOrderItemSerializer(many=True, read_only=True)
    invoice = ShopInvoiceSerializer(read_only=True, allow_null=True)
    store_name = serializers.CharField(source="organization.name", read_only=True)
    buyer_name = serializers.SerializerMethodField()
    buyer_email = serializers.EmailField(source="buyer.email", read_only=True)
    invoice_number = serializers.SerializerMethodField()

    class Meta:
        model = ShopOrder
        fields = [
            "id",
            "status",
            "delivery_status",
            "subtotal_cop",
            "discount_cop",
            "total_cop",
            "discount_code",
            "mp_preference_id",
            "mp_payment_id",
            "fulfilled",
            "items",
            "invoice",
            "invoice_number",
            "store_name",
            "buyer_name",
            "buyer_email",
            "created_at",
        ]

    def get_buyer_name(self, obj):
        buyer = obj.buyer
        return (getattr(buyer, "full_name", None) or "").strip() or buyer.email

    def get_invoice_number(self, obj):
        try:
            invoice = obj.invoice
        except ShopInvoice.DoesNotExist:
            return None
        return invoice.number if invoice else None
