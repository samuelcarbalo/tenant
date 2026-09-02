from django.core.management.base import BaseCommand

from authentication.bootstrap import (
    DEFAULT_EMAIL,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    ensure_platform_superuser,
)


class Command(BaseCommand):
    help = (
        "Crea el superusuario de plataforma si no existe "
        "(email/username + is_staff/is_superuser + créditos ilimitados)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", default=None)
        parser.add_argument("--password", default=None)
        parser.add_argument("--username", default=None)

    def handle(self, *args, **options):
        user, created = ensure_platform_superuser(
            email=options.get("email") or DEFAULT_EMAIL,
            password=options.get("password") or DEFAULT_PASSWORD,
            username=options.get("username") or DEFAULT_USERNAME,
        )
        action = "creado" if created else "actualizado"
        self.stdout.write(
            self.style.SUCCESS(
                f"Superusuario de plataforma {action}: {user.email} "
                f"(id={user.id}, admin_level={user.admin_level}, "
                f"unlimited_credits={user.is_unlimited_credits})"
            )
        )
