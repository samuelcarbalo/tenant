from django.core.management.base import BaseCommand

from payments.services.withdrawal_alert import check_withdrawal_alert


class Command(BaseCommand):
    help = "Verifica si hay fondos acumulados en MP y genera alerta de retiro ACH."

    def handle(self, *args, **options):
        alert = check_withdrawal_alert()
        if alert:
            self.stdout.write(self.style.WARNING(alert.message))
        else:
            self.stdout.write(self.style.SUCCESS("No se requiere alerta de retiro."))
