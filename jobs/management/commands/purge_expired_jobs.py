from django.core.management.base import BaseCommand

from jobs.services import purge_expired_job_offers, sync_all_job_offers_to_history


class Command(BaseCommand):
    help = (
        "Sincroniza el historial analítico de vacantes y elimina de JobOffer "
        "las ofertas con expires_at <= ahora (caducidad a 30 días)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync-only",
            action="store_true",
            help="Solo consolida el historial, sin borrar vacantes caducadas.",
        )

    def handle(self, *args, **options):
        synced = sync_all_job_offers_to_history()
        self.stdout.write(self.style.NOTICE(f"Historial sincronizado: {synced} ofertas activas."))
        if options.get("sync_only"):
            return
        result = purge_expired_job_offers()
        self.stdout.write(
            self.style.SUCCESS(
                f"Depuración completada. Candidatas: {result['candidates']}. "
                f"Eliminadas de JobOffer: {result['purged']}."
            )
        )
