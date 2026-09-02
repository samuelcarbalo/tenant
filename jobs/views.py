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
from core.permissions import resolve_request_organization, user_is_platform_elevated
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
        "is_external",
    ]
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
        """
        Filtrar ofertas por organización y estado.
        """
        user = self.request.user
        queryset = JobOffer.objects.select_related("organization", "posted_by")

        if user.is_authenticated and (
            user.role == "manager" or user_is_platform_elevated(user)
        ):
            my_offers = self.request.query_params.get("my_offers", "false")
            if my_offers.lower() == "true":
                if user_is_platform_elevated(user):
                    queryset = queryset.filter(posted_by=user)
                else:
                    queryset = queryset.filter(company_name=user.company_name)
        # Filtrar por organización si se especifica
        org_slug = self.request.query_params.get("organization")
        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)
        # Por defecto, mostrar solo activas y no expiradas
        show_expired = self.request.query_params.get("show_expired", "false")
        my_offers = self.request.query_params.get("my_offers", "false")
        if show_expired.lower() != "true":
            filters = {
                "is_active": True,
                "expires_at__gt": timezone.now(),
            }
            if my_offers.lower() != "true":
                filters["moderation_status"] = "approved"
            queryset = queryset.filter(**filters)

        return queryset

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        from django.db import transaction
        from authentication.models import User

        user = self.request.user
        print(f"DEBUG: User is {user} - Auth: {user.is_authenticated}")

        org = resolve_request_organization(self.request)
        company_name = user.company_name or (
            org.name if org else None
        ) or (
            user.get_full_name() if user_is_platform_elevated(user) else None
        ) or "Plataforma"
        print(f"DEBUG: Company name is {company_name}")
        if not org:
            raise ValidationError(
                {
                    "detail": "No se pudo resolver la organización. "
                    "Envía la cabecera X-Tenant o asigna una organización al usuario."
                }
            )

        # 3. Validar y restar créditos
        with transaction.atomic():
            fresh_user = User.objects.select_for_update().get(id=user.id)
            from authentication.credits import charge_credits

            user.credits = charge_credits(
                fresh_user,
                5,
                "No tienes suficientes créditos para publicar una oferta de empleo. "
                f"Publicar un empleo cuesta 5 créditos y actualmente tienes {fresh_user.credits} créditos.",
            )

            # 4. Si llegamos aquí, guardamos con seguridad
            serializer.save(
                organization=org,
                posted_by=user,
                company_name=company_name,
            )

    # ← AGREGAR ESTE MÉTODO
    def perform_update(self, serializer):
        """Forzar el company_name del usuario en actualizaciones"""
        from rest_framework.exceptions import ValidationError

        user = self.request.user

        # Siempre usar el company_name del usuario, ignorar lo del frontend
        org = resolve_request_organization(self.request)
        company_name = user.company_name or (
            org.name if org else None
        ) or (
            user.get_full_name() if user_is_platform_elevated(user) else None
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
        """Postularse a una oferta (interna o redirección externa)."""
        offer = self.get_object()

        if offer.is_expired:
            return Response(
                {"error": "Esta oferta ha expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = offer.applications.filter(applicant=request.user).first()

        if offer.is_external:
            if not offer.external_apply_url:
                return Response(
                    {"error": "Esta oferta externa no tiene URL de postulación."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if existing:
                return Response(
                    {
                        "success": True,
                        "redirected": True,
                        "already_applied": True,
                        "message": "Postulación externa ya registrada. Redirigiendo al sitio de la empresa.",
                        "external_apply_url": offer.external_apply_url,
                        "application_status": existing.status,
                    }
                )
            application = JobApplication.objects.create(
                offer=offer,
                applicant=request.user,
                status="redirected",
                cover_letter="",
            )
            return Response(
                {
                    "success": True,
                    "redirected": True,
                    "already_applied": False,
                    "message": "Postulación registrada como redirigida / aplicada externamente.",
                    "external_apply_url": offer.external_apply_url,
                    "application_status": application.status,
                },
                status=status.HTTP_201_CREATED,
            )

        if existing:
            return Response(
                {"error": "Ya te has postulado a esta oferta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = JobApplicationSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(offer=offer, applicant=request.user)

        return Response(
            {
                "success": True,
                "redirected": False,
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

        queryset = JobApplication.objects.select_related(
            "offer", "offer__organization", "applicant"
        )

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
