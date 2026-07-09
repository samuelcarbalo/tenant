from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

from .auth_utils import resolve_login_user

User = get_user_model()


class EmailOrganizationBackend(ModelBackend):
    """
    Backend de autenticación:
    - Con organization_slug → usuario del tenant
    - Sin organization_slug → superusuario de plataforma (sin org)
    """

    def authenticate(
        self, request, email=None, password=None, organization_slug=None, **kwargs
    ):
        if not email or not password:
            return None
        return resolve_login_user(email, password, organization_slug)
