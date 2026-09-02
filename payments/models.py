import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class PaymentOrder(models.Model):
    """Orden de pago pendiente o procesada vía Mercado Pago Checkout Pro."""

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("approved", "Aprobado"),
        ("rejected", "Rechazado"),
        ("cancelled", "Cancelado"),
        ("refunded", "Reembolsado"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_orders",
    )
    package_id = models.CharField(max_length=32, db_index=True)
    credits_amount = models.PositiveIntegerField()
    amount_cop = models.PositiveIntegerField()

    mp_preference_id = models.CharField(max_length=255, blank=True, db_index=True)
    mp_payment_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    credits_applied = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_orders"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} — {self.package_id} — {self.status}"


class TransaccionFacturacion(models.Model):
    """Registro fiscal de cada compra aprobada (DIAN / contabilidad)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_order = models.OneToOneField(
        PaymentOrder,
        on_delete=models.CASCADE,
        related_name="facturacion",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transacciones_facturacion",
    )

    monto_total = models.DecimalField(max_digits=12, decimal_places=2)
    comision_mercado_pago = models.DecimalField(max_digits=12, decimal_places=2)
    iva_comision = models.DecimalField(max_digits=12, decimal_places=2)
    monto_neto_recibido = models.DecimalField(max_digits=12, decimal_places=2)

    creditos_comprados = models.PositiveIntegerField()
    mp_payment_id = models.CharField(max_length=255, blank=True)
    package_id = models.CharField(max_length=32)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transacciones_facturacion"
        ordering = ["-created_at"]
        verbose_name = "Transacción de facturación"
        verbose_name_plural = "Transacciones de facturación"

    def __str__(self):
        return f"Factura {self.id} — ${self.monto_total}"


class WithdrawalAlert(models.Model):
    """Alerta administrativa para retiro ACH antes de los 180 días en MP."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.TextField()
    total_pending_cop = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    days_since_last_withdrawal = models.PositiveIntegerField(default=0)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "withdrawal_alerts"
        ordering = ["-created_at"]


class MercadoPagoWebhookEvent(models.Model):
    """
    Auditoría de notificaciones webhook de Mercado Pago.
    Complementa el historial de usuario (Notification) con el payload crudo.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.CharField(max_length=64, blank=True, db_index=True)
    action = models.CharField(max_length=64, blank=True)
    resource_id = models.CharField(max_length=128, blank=True, db_index=True)
    request_id = models.CharField(max_length=128, blank=True, db_index=True)
    signature_valid = models.BooleanField(default=False)
    live_mode = models.BooleanField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    payment_status = models.CharField(max_length=32, blank=True)
    payment_order = models.ForeignKey(
        PaymentOrder,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="webhook_events",
    )
    processed_ok = models.BooleanField(default=False)
    process_result = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mercadopago_webhook_events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["resource_id", "created_at"]),
        ]

    def __str__(self):
        return f"MP webhook {self.topic}:{self.resource_id} ({self.process_result})"
