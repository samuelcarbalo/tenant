from django.contrib import admin
from .models import RealEstateOffer


@admin.register(RealEstateOffer)
class RealEstateOfferAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organization",
        "price",
        "currency",
        "category",
        "property_type",
        "posted_at",
        "expires_at",
        "is_active",
    )
    list_filter = ("category", "property_type", "is_active", "posted_at")
    search_fields = ("title", "description", "location", "contact_name")
    raw_id_fields = ("organization", "posted_by")
