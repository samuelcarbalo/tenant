from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Limpia la cache de Django (incluye contadores de rate limiting / throttling)."

    def handle(self, *args, **options):
        cache.clear()
        self.stdout.write(self.style.SUCCESS("Cache limpiada. Throttling reseteado."))
