from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

# from django.db.models import Q
from django.utils import timezone
from django.db.models import F

from datetime import timedelta

from django_filters.rest_framework import DjangoFilterBackend

from .models import JobOffer, JobApplication
from .serializers import (
    JobOfferListSerializer,
    JobOfferDetailSerializer,
    JobOfferCreateUpdateSerializer,
    JobApplicationSerializer,
    JobApplicationUpdateSerializer,
)
from .permissions import IsManagerOfOrganization, CanApplyToJob


class JobOfferViewSet(viewsets.ModelViewSet):
    """
    ViewSet para ofertas de empleo.
    """

    queryset = JobOffer.objects.all()
    lookup_field = "pk"  # Usar UUID directamente
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        "job_type",
        "remote",
        "is_active",
        "organization",
        "category",
    ]  # ← AGREGAR category
    search_fields = ["title", "company_name", "description", "skills", "category"]
    ordering_fields = ["posted_at", "salary_min", "applications_count"]

    def get_serializer_class(self):
        if self.action == "list":
            return JobOfferListSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return JobOfferCreateUpdateSerializer
        return JobOfferDetailSerializer

    def get_permissions(self):
        # Permitir acceso público a listar y ver detalle
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        elif self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsManagerOfOrganization()]
        elif self.action == "apply":
            return [IsAuthenticated(), CanApplyToJob()]
        return [AllowAny()]

    def get_queryset(self):
        print(
            f"DEBUG: User is {self.request.user} - Auth: {self.request.user.is_authenticated}"
        )
        """
        Filtrar ofertas por organización y estado.
        """
        # Si es manager y pide "my_offers", filtrar por su organización
        # Filtrar solo activas y no expiradas para usuarios públicos
        user = self.request.user
        queryset = JobOffer.objects.select_related("organization", "posted_by")

        if user.is_authenticated and user.role == "manager":
            my_offers = self.request.query_params.get("my_offers", "false")
            if my_offers.lower() == "true":
                queryset = queryset.filter(company_name=user.company_name)
        # Filtrar por organización si se especifica
        org_slug = self.request.query_params.get("organization")
        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)
        # Por defecto, mostrar solo activas y no expiradas
        show_expired = self.request.query_params.get("show_expired", "false")
        if show_expired.lower() != "true":
            queryset = queryset.filter(is_active=True, expires_at__gt=timezone.now())

        return queryset

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError

        user = self.request.user
        print(f"DEBUG: User is {user} - Auth: {user.is_authenticated}")

        # 1. Intentar obtener el nombre (Prioridad: Usuario > Organización)
        company_name = user.company_name or (
            user.organization.name if user.organization else None
        )
        print(f"DEBUG: Company name is {company_name}")
        # 2. Hard check: Si no hay nombre, abortamos la operación
        if not company_name:
            raise ValidationError(
                {
                    "detail": "No se pudo determinar el nombre de la empresa. "
                    "El usuario o su organización deben tener un nombre asignado."
                }
            )

        # 3. Si llegamos aquí, guardamos con seguridad
        serializer.save(
            organization=user.organization,
            posted_by=user,
            company_name=company_name,
        )

    # ← AGREGAR ESTE MÉTODO
    def perform_update(self, serializer):
        """Forzar el company_name del usuario en actualizaciones"""
        from rest_framework.exceptions import ValidationError

        user = self.request.user

        # Siempre usar el company_name del usuario, ignorar lo del frontend
        company_name = user.company_name or (
            user.organization.name if user.organization else None
        )

        if not company_name:
            raise ValidationError(
                {
                    "detail": "No se pudo determinar el nombre de la empresa. "
                    "El usuario o su organización deben tener un nombre asignado."
                }
            )

        serializer.save(company_name=company_name)

    @action(detail=True, methods=["get"])
    def company_name(self, request, pk=None):
        offer = self.get_object()
        return Response({"company_name": offer.company_name})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        # Incremento atómico de vistas
        JobOffer.objects.filter(pk=instance.pk).update(views_count=F("views_count") + 1)

        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        """Renovar una oferta por 30 días más"""
        offer = self.get_object()

        if not offer.is_expired and offer.expires_at > timezone.now() + timedelta(
            days=25
        ):
            return Response(
                {"error": "La oferta aún tiene más de 5 días vigentes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        offer.renew(days=30)
        return Response(
            {
                "success": True,
                "message": "Oferta renovada por 30 días más.",
                "new_expiration": offer.expires_at,
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def apply(self, request, pk=None):
        """Postularse a una oferta"""
        offer = self.get_object()

        # Verificar que no esté expirada
        if offer.is_expired:
            return Response(
                {"error": "Esta oferta ha expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Verificar que no haya postulado ya
        if offer.applications.filter(applicant=request.user).exists():
            return Response(
                {"error": "Ya te has postulado a esta oferta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Crear postulación
        serializer = JobApplicationSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(offer=offer, applicant=request.user)

        # Incrementar contador
        # offer.applications_count += 1
        # offer.save()

        return Response(
            {
                "success": True,
                "message": "Postulación enviada exitosamente.",
                "application": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def applicants(self, request, pk=None):
        """Ver postulantes de una oferta (solo manager)"""
        offer = self.get_object()

        # Verificar que sea manager de la misma org
        if (
            request.user.role != "manager"
            or request.user.organization != offer.organization
        ):
            return Response(
                {"error": "No tienes permiso para ver esto."},
                status=status.HTTP_403_FORBIDDEN,
            )
        applications = offer.applications.select_related("applicant").all()
        serializer = JobApplicationSerializer(applications, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_offers(self, request):
        """
        Endpoint: /api/offers/my_offers/
        Filtra las ofertas basadas en el company_name del manager logueado.
        """
        user = request.user

        # Validamos que el usuario tenga un company_name
        if not user.company_name:
            return Response(
                {"error": "Tu perfil no tiene un company_name asociado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Filtramos el queryset base
        queryset = self.get_queryset().filter(company_name=user.company_name)

        # Aplicamos paginación si la tienes configurada en el proyecto
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class JobApplicationViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar postulaciones (reclutadores).
    """

    queryset = JobApplication.objects.all()
    serializer_class = JobApplicationSerializer

    def get_permissions(self):
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user

        if not user.is_authenticated:
            return JobApplication.objects.none()

        queryset = JobApplication.objects.select_related("offer", "applicant")

        # ADMIN: Filtrar por su company_name automáticamente
        # Filtro base por rol
        if user.role == "manager" and user.organization:
            if user.company_name:
                queryset = queryset.filter(offer__company_name=user.company_name)
        else:
            queryset = queryset.filter(applicant=user)

        # Nuevo filtro por company_name
        company = self.request.query_params.get("company")
        if company:
            queryset = queryset.filter(offer__company_name__icontains=company)

        return queryset

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return JobApplicationUpdateSerializer
        return JobApplicationSerializer

    def update(self, request, *args, **kwargs):
        """Solo managers pueden actualizar estado y notas"""
        application = self.get_object()
        user = request.user
        print(f"User role: {user.role}")
        print(f"User org: {user.organization}")
        print(f"Offer org: {application.offer.organization}")
        print(f"Son iguales: {user.organization == application.offer.organization}")
        # Solo managers pueden actualizar
        if (
            user.role != "manager"
            or user.organization != application.offer.organization
        ):
            return Response(
                {"error": "No tienes permiso para actualizar esta postulación."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().update(request, *args, **kwargs)
