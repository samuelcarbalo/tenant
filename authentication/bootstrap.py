"""Bootstrap del superusuario de plataforma (sin tenant)."""
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

DEFAULT_EMAIL = "carbalosamuel@hotmail.com"
DEFAULT_PASSWORD = "Vivayo123!"
DEFAULT_USERNAME = "carbalosamuel"


def ensure_platform_superuser(email=None, password=None, username=None):
    """
    Crea o actualiza el superusuario de plataforma.
    Retorna (user, created: bool).
    """
    email = (
        email
        or getattr(settings, "PLATFORM_SUPERUSER_EMAIL", None)
        or DEFAULT_EMAIL
    ).strip().lower()
    password = (
        password
        or getattr(settings, "PLATFORM_SUPERUSER_PASSWORD", None)
        or DEFAULT_PASSWORD
    )
    username = (username or DEFAULT_USERNAME).strip()

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
        user.admin_level = 1
        user.email_verified = True
        if not user.username:
            user.username = username
        user.set_password(password)
        user.save()

    changed_fields = []
    if not user.is_staff:
        user.is_staff = True
        changed_fields.append("is_staff")
    if not user.is_superuser:
        user.is_superuser = True
        changed_fields.append("is_superuser")
    if not user.is_active:
        user.is_active = True
        changed_fields.append("is_active")
    if not user.is_unlimited_credits:
        user.is_unlimited_credits = True
        changed_fields.append("is_unlimited_credits")
    if getattr(user, "admin_level", 0) != 1:
        user.admin_level = 1
        changed_fields.append("admin_level")
    if not user.email_verified:
        user.email_verified = True
        changed_fields.append("email_verified")
    if changed_fields:
        changed_fields.append("updated_at")
        user.save(update_fields=changed_fields)

    return user, created
