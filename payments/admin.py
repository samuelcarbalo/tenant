from django.contrib import admin

from payments.models import (
    MercadoPagoWebhookEvent,
    PaymentOrder,
    TransaccionFacturacion,
    WithdrawalAlert,
)


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "package_id", "amount_cop", "status", "credits_applied", "created_at")
    list_filter = ("status", "package_id", "credits_applied")
    search_fields = ("user__email", "mp_preference_id", "mp_payment_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TransaccionFacturacion)
class TransaccionFacturacionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "monto_total",
        "comision_mercado_pago",
        "iva_comision",
        "monto_neto_recibido",
        "creditos_comprados",
        "created_at",
    )
    list_filter = ("package_id",)
    search_fields = ("user__email", "mp_payment_id")
    readonly_fields = ("created_at",)


@admin.register(WithdrawalAlert)
class WithdrawalAlertAdmin(admin.ModelAdmin):
    list_display = ("id", "total_pending_cop", "days_since_last_withdrawal", "is_resolved", "created_at")
    list_filter = ("is_resolved",)
    readonly_fields = ("created_at",)


@admin.register(MercadoPagoWebhookEvent)
class MercadoPagoWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "topic",
        "resource_id",
        "payment_status",
        "signature_valid",
        "processed_ok",
        "process_result",
        "created_at",
    )
    list_filter = ("topic", "payment_status", "signature_valid", "processed_ok")
    search_fields = ("resource_id", "request_id", "process_result")
    readonly_fields = ("created_at", "payload")
