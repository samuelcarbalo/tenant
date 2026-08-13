from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError

from .models import RealEstateOffer
from .serializers import (
    RealEstateOfferListSerializer,
    RealEstateOfferDetailSerializer,
    RealEstateOfferCreateUpdateSerializer,
)
from .permissions import IsManagerOfOrganization


class RealEstateOfferViewSet(viewsets.ModelViewSet):
    """
    ViewSet para ofertas de bienes raíces.
    """

    queryset = RealEstateOffer.objects.all()
    lookup_field = "pk"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        "category",
        "property_type",
        "location",
        "is_active",
        "organization",
    ]
    search_fields = ["title", "description", "location", "contact_name"]
    ordering_fields = ["price", "posted_at", "views_count"]

    def get_serializer_class(self):
        if self.action == "list":
            return RealEstateOfferListSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return RealEstateOfferCreateUpdateSerializer
        return RealEstateOfferDetailSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        elif self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsManagerOfOrganization()]
        return [AllowAny()]

    def get_queryset(self):
        """
        Filtrar ofertas por organización, estado y vigencia.
        """
        user = self.request.user
        # Optimización N+1 queries
        queryset = RealEstateOffer.objects.select_related("organization", "posted_by")

        # Si el manager solicita sus propias ofertas
        if user.is_authenticated and user.role in ("manager", "admin"):
            my_offers = self.request.query_params.get("my_offers", "false")
            if my_offers.lower() == "true":
                queryset = queryset.filter(posted_by=user)

        # Filtrar por organización (slug o ID) si viene en query_params
        org_slug = self.request.query_params.get("organization")
        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)

        # Por defecto, usuarios no autenticados solo ven ofertas activas y no expiradas
        show_expired = self.request.query_params.get("show_expired", "false")
        my_offers = self.request.query_params.get("my_offers", "false")
        if show_expired.lower() != "true":
            filters = {"is_active": True, "expires_at__gt": timezone.now()}
            if my_offers.lower() != "true":
                filters["moderation_status"] = "approved"
            queryset = queryset.filter(**filters)

        return queryset

    def perform_create(self, serializer):
        """
        Lógica atómica para crear ofertas descontando 5 créditos.
        """
        user = self.request.user
        from authentication.models import User

        if not user.organization:
            raise ValidationError(
                {"detail": "Debes pertenecer a una organización para publicar."}
            )

        with transaction.atomic():
            # Bloquear la fila del usuario para evitar condiciones de carrera (Race Condition)
            fresh_user = User.objects.select_for_update().get(id=user.id)
            from authentication.credits import charge_credits

            user.credits = charge_credits(
                fresh_user,
                5,
                f"Créditos insuficientes. Cuesta 5 créditos publicar y tienes {fresh_user.credits}.",
            )

            # Guardar el registro de bienes raíces
            serializer.save(
                organization=user.organization,
                posted_by=user,
            )

    def retrieve(self, request, *args, **kwargs):
        """
        Incremento atómico de vistas al ver los detalles.
        """
        instance = self.get_object()
        RealEstateOffer.objects.filter(pk=instance.pk).update(
            views_count=F("views_count") + 1
        )
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_offers(self, request):
        """Listar propiedades publicadas por el manager autenticado."""
        if request.user.role not in ("manager", "admin"):
            return Response(
                {"error": "Solo managers pueden ver sus publicaciones."},
                status=status.HTTP_403_FORBIDDEN,
            )
        queryset = (
            RealEstateOffer.objects.filter(posted_by=request.user)
            .select_related("organization", "posted_by")
            .order_by("-posted_at")
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsManagerOfOrganization])
    def renew(self, request, pk=None):
        """
        Renovar la publicación de bienes raíces por 30 días más.
        """
        offer = self.get_object()
        if request.user.role not in ("manager", "admin") or request.user.organization != offer.organization:
            return Response(
                {"error": "No tienes permiso para renovar esta oferta."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Solo permitir renovar si expira pronto (menos de 5 días)
        if not offer.is_expired and offer.expires_at > timezone.now() + timedelta(
            days=25
        ):
            return Response(
                {"error": "La oferta aún está vigente por más de 5 días."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        offer.renew(days=30)
        return Response(
            {
                "success": True,
                "message": "Publicación renovada por 30 días.",
                "new_expiration": offer.expires_at,
            }
        )
