from rest_framework import permissions


class IsManagerOrReadOnly(permissions.BasePermission):
    """
    Permiso: solo managers pueden crear/editar/eliminar ofertas.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role == 'manager'


class IsManagerOfOrganization(permissions.BasePermission):
    """
    Permiso: solo managers de la misma organización pueden gestionar ofertas.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return (
            request.user.is_authenticated and 
            request.user.role == 'manager' and
            obj.organization == request.user.organization
        )


class CanApplyToJob(permissions.BasePermission):
    """
    Permiso: usuarios normales pueden postularse.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'user'