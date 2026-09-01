import traceback

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Diagnóstico SMTP: imprime la config de correo (sin la contraseña) "
        "y envía un mensaje de prueba. "
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
        host = getattr(settings, "EMAIL_HOST", "")
        port = getattr(settings, "EMAIL_PORT", "")
        user = getattr(settings, "EMAIL_HOST_USER", "")
        use_tls = getattr(settings, "EMAIL_USE_TLS", False)
        use_ssl = getattr(settings, "EMAIL_USE_SSL", False)
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        has_password = bool(getattr(settings, "EMAIL_HOST_PASSWORD", ""))

        self.stdout.write(f"BACKEND: {backend}")
        self.stdout.write(f"HOST: {host}:{port}")
        self.stdout.write(f"USER: {user}")
        self.stdout.write(f"TLS: {use_tls} | SSL: {use_ssl}")
        self.stdout.write(f"FROM: {from_email}")
        self.stdout.write(f"PASSWORD configurada: {'sí' if has_password else 'NO'}")
        self.stdout.write(f"TO: {to_email}")

        if not host or not user or not has_password:
            raise CommandError(
                "SMTP incompleto: define EMAIL_HOST, EMAIL_HOST_USER y "
                "EMAIL_HOST_PASSWORD en el entorno / .env de Render."
            )

        try:
            sent = send_mail(
                subject="Test Chéver",
                message="Mensaje de prueba de recuperación de contraseña",
                from_email=from_email,
                recipient_list=[to_email],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f"CORREO ENVIADO CON EXITO ({sent})"))
        except Exception as exc:
            self.stderr.write(self.style.ERROR("ERROR AL ENVIAR CORREO:"))
            self.stderr.write(str(exc))
            traceback.print_exc()
            raise CommandError(exc) from exc
