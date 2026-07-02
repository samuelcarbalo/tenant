"""Acredita un pago de Mercado Pago manualmente (útil en local, sin webhook público).

Uso típico tras pagar en sandbox:
    python manage.py apply_payment <payment_id>

Para desarrollo puro sin pasar por MP, se puede acreditar una orden directamente:
    python manage.py apply_payment --order <order_id> --force
"""
from django.core.management.base import BaseCommand, CommandError

from payments.models import PaymentOrder
from payments.services.payment_processor import apply_approved_payment


class Command(BaseCommand):
    help = "Acredita créditos de un pago de Mercado Pago (reconciliación manual)."

    def add_arguments(self, parser):
        parser.add_argument(
            "payment_id",
            nargs="?",
            help="ID del pago en Mercado Pago (lo muestra el checkout de prueba).",
        )
        parser.add_argument(
            "--order",
            dest="order_id",
            help="Aplica directamente esta orden (dev, omite consultar a MP).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Con --order: acredita aunque no se verifique el pago en MP.",
        )

    def handle(self, *args, **options):
        payment_id = options.get("payment_id")
        order_id = options.get("order_id")
        force = options.get("force")

        # Camino dev: acreditar una orden sin consultar a MP
        if order_id:
            try:
                order = PaymentOrder.objects.get(id=order_id)
            except PaymentOrder.DoesNotExist:
                raise CommandError(f"Orden no encontrada: {order_id}")
            if not force:
                raise CommandError(
                    "Usa --force para acreditar una orden sin verificar el pago en MP."
                )
            applied = apply_approved_payment(order, mp_payment_id=payment_id or "manual")
            self._report(order, applied)
            return

        if not payment_id:
            raise CommandError("Debes indicar un payment_id o usar --order <id> --force.")

        # Camino normal: verificar el pago en Mercado Pago
        from payments.services.mercadopago_service import MercadoPagoService

        try:
            mp = MercadoPagoService()
            payment = mp.get_payment(str(payment_id))
        except Exception as exc:
            raise CommandError(f"No se pudo consultar el pago en MP: {exc}")

        mp_status = payment.get("status")
        if mp_status != "approved":
            raise CommandError(
                f"El pago {payment_id} no está aprobado (estado: {mp_status})."
            )

        external_ref = payment.get("external_reference")
        if not external_ref:
            raise CommandError("El pago no tiene external_reference (orden asociada).")

        try:
            order = PaymentOrder.objects.get(id=external_ref)
        except PaymentOrder.DoesNotExist:
            raise CommandError(f"Orden no encontrada para la referencia: {external_ref}")

        applied = apply_approved_payment(order, str(payment_id))
        self._report(order, applied)

    def _report(self, order, applied):
        order.refresh_from_db()
        if applied:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Créditos acreditados: +{order.credits_amount} a {order.user.email} "
                    f"(orden {order.id})."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"La orden {order.id} ya tenía los créditos aplicados (idempotente)."
                )
            )
