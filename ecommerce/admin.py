from django.contrib import admin

from ecommerce.models import (
    Category,
    Discount,
    Product,
    ProductDiscount,
    ShopOrder,
    ShopOrderItem,
    SubCategory,
)


class ShopOrderItemInline(admin.TabularInline):
    model = ShopOrderItem
    extra = 0
    readonly_fields = (
        "product_name",
        "product_sku",
        "unit_price_cop",
        "quantity",
        "line_total_cop",
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "organization", "sort_order", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "slug", "organization", "sort_order", "is_active")
    list_filter = ("organization", "category", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "price_cop",
        "stock",
        "category",
        "subcategory",
        "is_published",
        "is_featured",
        "organization",
    )
    list_filter = ("organization", "is_published", "is_featured", "category")
    search_fields = ("name", "sku", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ProductDiscount)
class ProductDiscountAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "discount_type",
        "discount_percentage",
        "start_time",
        "end_time",
        "is_flash_sale",
        "is_active",
        "organization",
    )
    list_filter = ("discount_type", "is_flash_sale", "is_active", "organization")
    search_fields = ("name",)
    filter_horizontal = ("products",)


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "discount_type",
        "value",
        "used_count",
        "is_active",
        "organization",
    )
    list_filter = ("discount_type", "is_active", "organization")
    search_fields = ("code", "name")


@admin.register(ShopOrder)
class ShopOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "buyer",
        "status",
        "total_cop",
        "discount_code",
        "fulfilled",
        "created_at",
    )
    list_filter = ("status", "fulfilled", "organization")
    search_fields = ("id", "buyer__email", "mp_payment_id")
    inlines = [ShopOrderItemInline]
