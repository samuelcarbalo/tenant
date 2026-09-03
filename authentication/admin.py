from django.contrib import admin

from authentication.models import CreditSubscriptionTransaction


@admin.register(CreditSubscriptionTransaction)
class CreditSubscriptionTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "transaction_type",
        "credits_spent",
        "days_granted",
        "expires_at",
        "created_at",
    )
    list_filter = ("transaction_type",)
    search_fields = ("user__email",)
    readonly_fields = ("id", "created_at", "updated_at")

