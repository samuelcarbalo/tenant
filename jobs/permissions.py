from rest_framework import permissions

from core.permissions import user_can_manage_content, user_is_platform_elevated


class IsManagerOrReadOnly(permissions.BasePermission):
    """
    Lectura pública; escritura para managers de org o admins/superusuarios de plataforma.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return user_can_manage_content(request.user)


class IsManagerOfOrganization(permissions.BasePermission):
    """
    Escritura: managers de la misma organización, o plataforma elevated (superuser/staff/admin).
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return user_can_manage_content(request.user)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user_is_platform_elevated(user):
            return True
        return (
            getattr(user, "role", None) == "manager"
            and getattr(obj, "organization", None) == user.organization
        )


class CanApplyToJob(permissions.BasePermission):
    """
    Permiso: usuarios normales pueden postularse.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "user"
