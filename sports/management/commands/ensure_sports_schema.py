"""
Repara el schema de sports en producción/test.

Si django_migrations marca 0027 como aplicada pero falta players.phone
(u otras columnas recientes), las crea. Evita el 503
"column players.phone does not exist" en match-events y alineaciones.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

SPORTS_0027 = "0027_player_phone"
SPORTS_0028 = "0028_matchevent_foul"
REQUIRED_PLAYER_COLUMNS = ("phone",)


class Command(BaseCommand):
    help = "Crea columnas de sports (p. ej. players.phone) si faltan en producción."

    def handle(self, *args, **options):
        from sports.models import Player

        try:
            call_command("migrate", "sports", interactive=False, verbosity=1)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.WARNING(f"migrate sports inicial: {exc}"))

        self._ensure_player_columns(Player)
        self._sync_migration_history(Player)

        try:
            call_command("migrate", "sports", interactive=False, verbosity=1)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.WARNING(f"migrate sports posterior: {exc}"))

        self._assert_schema(Player)
        self.stdout.write(self.style.SUCCESS("sports schema OK"))

    def _table_columns(self, table: str) -> set[str]:
        with connection.cursor() as cursor:
            try:
                description = connection.introspection.get_table_description(cursor, table)
            except Exception:
                return set()
        return {col.name for col in description}

    def _ensure_player_columns(self, player_model):
        table = player_model._meta.db_table
        existing = self._table_columns(table)
        if not existing:
            self.stderr.write(
                self.style.WARNING(f"La tabla {table} no existe aún; se deja a migrate.")
            )
            return
        with connection.schema_editor() as editor:
            for name in REQUIRED_PLAYER_COLUMNS:
                field = player_model._meta.get_field(name)
                if field.column in existing:
                    continue
                editor.add_field(player_model, field)
                self.stdout.write(
                    self.style.SUCCESS(f"columna {table}.{field.column} creada")
                )

    def _sync_migration_history(self, player_model):
        cols = self._table_columns(player_model._meta.db_table)
        schema_ready = all(c in cols for c in REQUIRED_PLAYER_COLUMNS)
        if not schema_ready:
            return
        recorder = MigrationRecorder(connection)
        applied = recorder.applied_migrations()
        for name in (SPORTS_0027, SPORTS_0028):
            if ("sports", name) not in applied:
                recorder.record_applied("sports", name)
                self.stdout.write(f"django_migrations: sports.{name} marcada como aplicada")

    def _assert_schema(self, player_model):
        cols = self._table_columns(player_model._meta.db_table)
        missing = [c for c in REQUIRED_PLAYER_COLUMNS if c not in cols]
        if missing:
            raise SystemExit(
                f"ensure_sports_schema falló; siguen faltando: {missing}"
            )
