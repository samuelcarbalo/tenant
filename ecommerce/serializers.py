from rest_framework import serializers

from ecommerce.models import Category, Discount, Product, ShopOrder, ShopOrderItem


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


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    category_slug = serializers.SerializerMethodField()

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
            "created_at",
        ]

    def get_category_name(self, obj):
        category = getattr(obj, "category", None)
        return getattr(category, "name", None) if category is not None else None

    def get_category_slug(self, obj):
        category = getattr(obj, "category", None)
        return getattr(category, "slug", None) if category is not None else None


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


class ShopOrderSerializer(serializers.ModelSerializer):
    items = ShopOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = ShopOrder
        fields = [
            "id",
            "status",
            "subtotal_cop",
            "discount_cop",
            "total_cop",
            "discount_code",
            "mp_preference_id",
            "mp_payment_id",
            "fulfilled",
            "items",
            "created_at",
        ]
