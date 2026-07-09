from rest_framework import permissions


class IsManagerOfOrganization(permissions.BasePermission):
    """
    Permiso: solo managers de la misma organización pueden gestionar las ofertas de bienes raíces.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return getattr(request.user, "role", None) in ("manager", "admin")

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return (
            request.user.is_authenticated
            and request.user.role == "manager"
            and obj.organization == request.user.organization
        )
