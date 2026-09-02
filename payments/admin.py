from django.contrib import admin
from django.forms import PasswordInput
from django.shortcuts import redirect
from django.urls import reverse

from payments.models import (
    MercadoPagoConfig,
    MercadoPagoWebhookEvent,
    PaymentOrder,
    TransaccionFacturacion,
    WithdrawalAlert,
)


@admin.register(MercadoPagoConfig)
class MercadoPagoConfigAdmin(admin.ModelAdmin):
    list_display = ("environment_status", "is_production", "updated_at")
    fieldsets = (
        (
            "Entorno activo",
            {
                "fields": ("is_production",),
                "description": (
                    "Desactivado = Sandbox/Test. Activado = Producción (Live). "
                    "El SDK usará las credenciales del bloque correspondiente."
                ),
            },
        ),
        (
            "Credenciales de prueba (Test / Sandbox)",
            {"fields": ("public_key_test", "access_token_test")},
        ),
        (
            "Credenciales de producción (Live)",
            {
                "fields": (
                    "public_key_prod",
                    "access_token_prod",
                    "client_id_prod",
                    "client_secret_prod",
                ),
            },
        ),
        ("Auditoría", {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)

    @admin.display(description="Entorno Activo")
    def environment_status(self, obj):
        return "🟢 PRODUCCIÓN" if obj.is_production else "🟡 PRUEBAS (TEST)"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in (
            "access_token_test",
            "access_token_prod",
            "client_secret_prod",
        ):
            kwargs["widget"] = PasswordInput(render_value=True)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def has_add_permission(self, request):
        if MercadoPagoConfig.objects.filter(pk=MercadoPagoConfig.SINGLETON_PK).exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Singleton: abrir el formulario de edición directamente."""
        obj = MercadoPagoConfig.load()
        url = reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
            args=(obj.pk,),
        )
        return redirect(url)


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
