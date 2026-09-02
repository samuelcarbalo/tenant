import traceback

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.email import resend_is_configured, send_system_email


class Command(BaseCommand):
    help = (
        "Diagnóstico de correo: imprime la config (sin secretos) "
        "y envía un mensaje de prueba por Resend HTTP. "
        "Uso: python manage.py send_test_email --settings=config.settings.production"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            default="carbal087@gmail.com",
            help="Destinatario de la prueba",
        )

    def handle(self, *args, **options):
        to_email = options["to"]
        backend = getattr(settings, "EMAIL_BACKEND", "")
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        has_resend = resend_is_configured()

        self.stdout.write(f"BACKEND: {backend}")
        self.stdout.write(f"FROM: {from_email}")
        self.stdout.write(f"RESEND_API_KEY: {'sí' if has_resend else 'NO'}")
        self.stdout.write(f"TO: {to_email}")

        if not has_resend and not getattr(settings, "DEBUG", False):
            raise CommandError(
                "RESEND_API_KEY no está definida. Render bloquea SMTP; "
                "configura RESEND_API_KEY en el entorno."
            )

        try:
            sent = send_system_email(
                subject="Test Chéver",
                message="Mensaje de prueba de recuperación de contraseña",
                recipient_list=[to_email],
            )
            self.stdout.write(self.style.SUCCESS(f"CORREO ENVIADO CON EXITO ({sent})"))
        except Exception as exc:
            self.stderr.write(self.style.ERROR("ERROR AL ENVIAR CORREO:"))
            self.stderr.write(str(exc))
            traceback.print_exc()
            raise CommandError(exc) from exc
