"""
Repara el schema de jobs en producción.

Si django_migrations marca 0005 como aplicada pero faltan columnas
(is_external / external_apply_url), las crea. Si las columnas existen
pero 0005 no está registrada, la marca aplicada para no reintentar AddField.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

JOBS_0005 = "0005_joboffer_external_and_history"
REQUIRED_JOB_OFFER_COLUMNS = ("is_external", "external_apply_url")


class Command(BaseCommand):
    help = "Crea columnas/tablas de vacantes externas si faltan en producción."

    def handle(self, *args, **options):
        from jobs.models import JobOffer, JobOfferHistory

        try:
            call_command("migrate", "jobs", interactive=False, verbosity=1)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.WARNING(f"migrate jobs inicial: {exc}"))

        self._ensure_job_offer_columns(JobOffer)
        self._ensure_history_table(JobOfferHistory)
        self._ensure_indexes(JobOffer)
        self._sync_migration_history()

        try:
            call_command("migrate", "jobs", interactive=False, verbosity=1)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.WARNING(f"migrate jobs posterior: {exc}"))

        self._assert_schema(JobOffer)
        self.stdout.write(self.style.SUCCESS("jobs schema OK"))

    def _table_columns(self, table: str) -> set[str]:
        with connection.cursor() as cursor:
            try:
                description = connection.introspection.get_table_description(cursor, table)
            except Exception:
                return set()
        return {col.name for col in description}

    def _ensure_job_offer_columns(self, job_offer_model):
        table = job_offer_model._meta.db_table
        existing = self._table_columns(table)
        if not existing:
            self.stderr.write(self.style.WARNING(f"La tabla {table} no existe aún; se deja a migrate."))
            return
        with connection.schema_editor() as editor:
            for name in REQUIRED_JOB_OFFER_COLUMNS:
                field = job_offer_model._meta.get_field(name)
                if field.column in existing:
                    continue
                editor.add_field(job_offer_model, field)
                self.stdout.write(self.style.SUCCESS(f"columna {table}.{field.column} creada"))

    def _ensure_history_table(self, history_model):
        tables = set(connection.introspection.table_names())
        table = history_model._meta.db_table
        if table in tables:
            return
        with connection.schema_editor() as editor:
            editor.create_model(history_model)
        self.stdout.write(self.style.SUCCESS(f"tabla {table} creada"))

    def _ensure_indexes(self, job_offer_model):
        table = job_offer_model._meta.db_table
        if connection.vendor != "postgresql":
            return
        if "is_external" not in self._table_columns(table):
            return
        with connection.cursor() as cursor:
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS job_offers_is_exte_529be5_idx '
                'ON "' + table.replace('"', "") + '" (is_external, expires_at)'
            )

    def _sync_migration_history(self):
        from jobs.models import JobOffer, JobOfferHistory

        offer_cols = self._table_columns(JobOffer._meta.db_table)
        tables = set(connection.introspection.table_names())
        schema_ready = (
            "is_external" in offer_cols
            and "external_apply_url" in offer_cols
            and JobOfferHistory._meta.db_table in tables
        )
        if not schema_ready:
            return
        recorder = MigrationRecorder(connection)
        applied = recorder.applied_migrations()
        if ("jobs", JOBS_0005) not in applied:
            recorder.record_applied("jobs", JOBS_0005)
            self.stdout.write(f"django_migrations: jobs.{JOBS_0005} marcada como aplicada")

    def _assert_schema(self, job_offer_model):
        from jobs.models import JobOfferHistory

        cols = self._table_columns(job_offer_model._meta.db_table)
        missing = [c for c in REQUIRED_JOB_OFFER_COLUMNS if c not in cols]
        tables = set(connection.introspection.table_names())
        history_table = JobOfferHistory._meta.db_table
        if history_table not in tables:
            missing.append(history_table)
        if missing:
            raise SystemExit(
                f"ensure_jobs_schema falló; siguen faltando: {missing}"
            )
