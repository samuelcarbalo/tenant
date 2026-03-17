from rest_framework import permissions


class IsOrganizationMember(permissions.BasePermission):
    """
    Permiso que verifica si el usuario pertenece a la organización
    especificada en el request (header o body).
    """
    def has_permission(self, request, view):
        # Superusers tienen acceso a todo
        if request.user.is_superuser:
            return True
        
        # Obtener organization_id del header o del usuario
        org_id = request.headers.get('X-Organization-ID')
        if not org_id:
            org_id = getattr(request.user, 'organization_id', None)
        
        if not org_id:
            return False
            
        return str(request.user.organization_id) == str(org_id)


class IsOrganizationAdmin(permissions.BasePermission):
    """
    Permiso para administradores de organización.
    """
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        
        return (
            request.user.is_staff and 
            request.user.role == 'admin'
        )