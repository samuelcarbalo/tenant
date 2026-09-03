from django.core.management.base import BaseCommand

from authentication.sports_subscription import expire_stale_sports_modules


class Command(BaseCommand):
    help = "Marca sports_module_active=False cuando sports_module_expires_at ya venció."

    def handle(self, *args, **options):
        updated = expire_stale_sports_modules()
        self.stdout.write(
            self.style.SUCCESS(f"Suscripciones deportivas expiradas: {updated}")
        )
