from django.contrib import admin

from ecommerce.models import (
    Category,
    Discount,
    Product,
    ProductDiscount,
    ShopInvoice,
    ShopOrder,
    ShopOrderItem,
    StoreSettings,
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
        "created_by",
    )
    list_filter = ("organization", "is_published", "is_featured", "category")
    search_fields = ("name", "sku", "slug")
    raw_id_fields = ("created_by",)
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


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ("organization", "store_logo", "updated_at")
    search_fields = ("organization__name", "organization__slug")


@admin.register(ShopOrder)
class ShopOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "buyer",
        "status",
        "delivery_status",
        "total_cop",
        "discount_code",
        "fulfilled",
        "created_at",
    )
    list_filter = ("status", "delivery_status", "fulfilled", "organization")
    search_fields = ("id", "buyer__email", "mp_payment_id")
    inlines = [ShopOrderItemInline]


@admin.register(ShopInvoice)
class ShopInvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "buyer_email", "seller_name", "total_cop", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("number", "buyer_email", "buyer_name")
