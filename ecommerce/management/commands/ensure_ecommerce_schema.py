"""
Garantiza tablas ecommerce en producción.

Si django_migrations marca ecommerce como aplicado pero las tablas no existen
(caso típico tras deploy parcial), limpia el historial de esa app y re-ejecuta migrate.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

REQUIRED_TABLES = (
    "ecommerce_categories",
    "ecommerce_products",
    "ecommerce_discounts",
    "ecommerce_orders",
    "ecommerce_order_items",
)


class Command(BaseCommand):
    help = "Crea tablas ecommerce si faltan (repara historial de migraciones inconsistente)."

    def handle(self, *args, **options):
        existing = set(connection.introspection.table_names())
        missing = [t for t in REQUIRED_TABLES if t not in existing]

        if not missing:
            self.stdout.write(self.style.SUCCESS("ecommerce schema OK"))
            return

        self.stderr.write(
            self.style.WARNING(f"Tablas ecommerce faltantes: {', '.join(missing)}")
        )

        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM django_migrations WHERE app = %s", ["ecommerce"])
            deleted = cursor.rowcount
        self.stdout.write(f"Registros django_migrations ecommerce eliminados: {deleted}")

        call_command("migrate", "ecommerce", interactive=False, verbosity=1)

        existing = set(connection.introspection.table_names())
        still_missing = [t for t in REQUIRED_TABLES if t not in existing]
        if still_missing:
            raise SystemExit(
                f"ensure_ecommerce_schema falló; siguen faltando: {still_missing}"
            )

        self.stdout.write(self.style.SUCCESS("ecommerce schema creado correctamente"))
