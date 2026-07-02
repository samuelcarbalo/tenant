from rest_framework import permissions

from .services import user_can_access_conversation


class IsConversationParticipant(permissions.BasePermission):
    """Solo participantes pueden acceder a una conversación."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        return user_can_access_conversation(request.user, obj)


class IsMessageSender(permissions.BasePermission):
    """Solo el remitente puede editar o eliminar su mensaje."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return obj.sender_id == request.user.id
