from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ContactMessage
from .permissions import IsSuperUser
from .serializers import (
    ContactMessageCreateSerializer,
    ContactMessageSerializer,
    ContactMessageUpdateSerializer,
)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class ContactMessageViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    POST /api/v1/contact/messages/ — público (guarda en BD).
    GET  /api/v1/contact/messages/ — solo superusuario.
    PATCH /api/v1/contact/messages/{id}/ — marcar leído (superusuario).
    """

    queryset = ContactMessage.objects.select_related("organization", "user")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_read"]
    search_fields = ["name", "email", "subject", "message"]
    ordering_fields = ["created_at", "is_read"]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return ContactMessageCreateSerializer
        if self.action in ("update", "partial_update"):
            return ContactMessageUpdateSerializer
        return ContactMessageSerializer

    def get_permissions(self):
        if self.action == "create":
            return [AllowAny()]
        return [IsSuperUser()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = getattr(request, "current_organization", None)
        user = request.user if request.user.is_authenticated else None

        instance = ContactMessage.objects.create(
            organization=organization,
            user=user,
            ip_address=_client_ip(request),
            **serializer.validated_data,
        )

        output = ContactMessageSerializer(instance)
        return Response(
            {
                "message": "Tu mensaje fue enviado correctamente. Te responderemos pronto.",
                "data": output.data,
            },
            status=status.HTTP_201_CREATED,
        )
