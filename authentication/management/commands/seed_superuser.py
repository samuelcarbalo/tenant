from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

DEFAULT_EMAIL = "carbalosamuel@hotmail.com"
DEFAULT_PASSWORD = "Vivayo123!"
DEFAULT_USERNAME = "carbalosamuel"


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
        email = (
            options.get("email")
            or getattr(settings, "PLATFORM_SUPERUSER_EMAIL", None)
            or DEFAULT_EMAIL
        ).strip().lower()
        password = (
            options.get("password")
            or getattr(settings, "PLATFORM_SUPERUSER_PASSWORD", None)
            or DEFAULT_PASSWORD
        )
        username = (options.get("username") or DEFAULT_USERNAME).strip()

        user = (
            User.objects.filter(email__iexact=email, organization__isnull=True)
            .order_by("-is_superuser")
            .first()
        )

        created = False
        if user is None:
            user = User.objects.create_superuser(
                email=email,
                username=username,
                password=password,
                first_name="Samuel",
                last_name="Carbalo",
                role="admin",
                user_type="person",
            )
            created = True
        else:
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            user.role = "admin"
            user.email_verified = True
            if not user.username:
                user.username = username
            user.save()

        changed = False
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if not user.is_unlimited_credits:
            user.is_unlimited_credits = True
            changed = True
        if not user.email_verified:
            user.email_verified = True
            changed = True
        if changed:
            user.save(
                update_fields=[
                    "is_staff",
                    "is_superuser",
                    "is_active",
                    "is_unlimited_credits",
                    "email_verified",
                    "updated_at",
                ]
            )

        # Perfil requiere organización; el superusuario de plataforma no tiene tenant.
        # No se crea Profile para evitar FK nula.

        action = "creado" if created else "actualizado"
        self.stdout.write(
            self.style.SUCCESS(
                f"Superusuario de plataforma {action}: {user.email} "
                f"(id={user.id}, unlimited_credits={user.is_unlimited_credits})"
            )
        )
