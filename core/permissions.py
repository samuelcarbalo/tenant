from rest_framework import permissions


class IsCoachOfTeam(permissions.BasePermission):
    """
    Permiso que verifica si el usuario autenticado es el coach (coach_email) del equipo.
    Se usa para crear/editar/eliminar jugadores de un equipo específico.
    """

    def has_permission(self, request, view):
        # Para acciones de lista/retrieve, permitir si es coach de algún equipo
        if view.action in ["list", "retrieve"]:
            return True
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # obj puede ser Player, Team, etc.
        if not request.user or not request.user.is_authenticated:
            return False

        # Si es superuser, permitir todo
        if request.user.is_superuser:
            return True

        # Obtener el equipo del jugador
        if hasattr(obj, "team"):
            team = obj.team
        elif hasattr(obj, "tournament"):
            # obj es un Team
            team = obj
        else:
            return False

        # Verificar si el email del usuario coincide con coach_email del equipo
        return request.user.email == team.coach_email


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
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            org_id = getattr(request.user, "organization_id", None)

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

        return request.user.is_staff and request.user.role == "admin"
