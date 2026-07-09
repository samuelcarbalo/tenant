from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "is_read", "organization", "created_at")
    list_filter = ("is_read", "organization", "created_at")
    search_fields = ("name", "email", "subject", "message")
    readonly_fields = ("created_at", "updated_at", "ip_address", "user", "organization")
    ordering = ("-created_at",)
