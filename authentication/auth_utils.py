"""
Utilidades de autenticación multi-tenant y plataforma.
"""
from django.contrib.auth import get_user_model

User = get_user_model()


def authenticate_tenant_user(email: str, password: str, organization_slug: str):
    """Autentica un usuario dentro de una organización (tenant)."""
    try:
        user = User.objects.select_related("organization").get(
            email=email,
            organization__slug=organization_slug,
            is_active=True,
        )
    except User.DoesNotExist:
        return None

    if user.check_password(password):
        return user
    return None


def authenticate_platform_user(email: str, password: str):
    """
    Autentica un superusuario de plataforma sin organización asignada.
    Estos usuarios gestionan tenants y no pertenecen a uno específico.
    """
    try:
        user = User.objects.select_related("organization").get(
            email=email,
            is_superuser=True,
            organization__isnull=True,
            is_active=True,
        )
    except User.DoesNotExist:
        return None

    if user.check_password(password):
        return user
    return None


def resolve_login_user(email: str, password: str, organization_slug: str | None = None):
    """
    Resuelve login según contexto:
    - Con organization_slug → login tenant
    - Sin organization_slug → login superusuario de plataforma
    """
    org_slug = (organization_slug or "").strip()

    if org_slug:
        return authenticate_tenant_user(email, password, org_slug)
    return authenticate_platform_user(email, password)
