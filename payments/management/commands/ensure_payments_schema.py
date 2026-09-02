"""
Garantiza la tabla mercadopago_config y la fila singleton (id=1) en producción.

Si django_migrations marca payments como aplicado pero la tabla no existe
(caso típico tras un deploy parcial en Neon), crea el modelo y el registro.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

REQUIRED_TABLE = "mercadopago_config"


class Command(BaseCommand):
    help = "Crea mercadopago_config si falta y asegura la fila singleton id=1."

    def handle(self, *args, **options):
        try:
            call_command("migrate", "payments", interactive=False, verbosity=1)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.WARNING(f"migrate payments inicial: {exc}"))

        existing = set(connection.introspection.table_names())
        if REQUIRED_TABLE not in existing:
            from payments.models import MercadoPagoConfig

            with connection.schema_editor() as editor:
                editor.create_model(MercadoPagoConfig)
            self.stdout.write(self.style.SUCCESS(f"tabla {REQUIRED_TABLE} creada"))

        from payments.models import MercadoPagoConfig

        MercadoPagoConfig.objects.get_or_create(
            id=1,
            defaults={"is_production": False},
        )
        self.stdout.write(self.style.SUCCESS("payments schema OK"))
