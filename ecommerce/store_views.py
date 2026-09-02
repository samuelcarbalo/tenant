"""API pública de lectura / staff-only de escritura para el logo de tienda."""

from django.db import DatabaseError, OperationalError, ProgrammingError
from rest_framework import status
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import resolve_request_organization
from ecommerce.models import StoreSettings
from ecommerce.store_serializers import StoreSettingsSerializer

_TABLE_MISSING = "La tabla de configuración aún no existe en la base de datos."


class IsStaffWriteOrPublicRead(BasePermission):
    """GET público; mutaciones solo is_staff / is_superuser."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return bool(user.is_staff or user.is_superuser)


def _organization(request):
    org = resolve_request_organization(request)
    if org is None:
        org = getattr(request, "current_organization", None)
    return org


def _get_or_create_settings(request, *, create: bool):
    org = _organization(request)
    if org is None:
        return None, Response(
            {"detail": "No hay organización activa (X-Tenant)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        if create:
            settings_obj, _ = StoreSettings.objects.get_or_create(organization=org)
            return settings_obj, None
        return StoreSettings.objects.filter(organization=org).first(), None
    except (ProgrammingError, OperationalError, DatabaseError):
        return None, Response(
            {"detail": _TABLE_MISSING, "store_logo": None},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class StoreSettingsAPIView(APIView):
    """GET/PATCH /api/v1/store/settings/"""

    permission_classes = [IsStaffWriteOrPublicRead]

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsStaffWriteOrPublicRead()]
        return [IsAuthenticated(), IsStaffWriteOrPublicRead()]

    def get(self, request, *args, **kwargs):
        org = _organization(request)
        try:
            qs = StoreSettings.objects.all()
            if org is not None:
                qs = qs.filter(organization=org)
            settings_obj = qs.first()
            logo_url = None
            if settings_obj and settings_obj.store_logo:
                logo_url = settings_obj.store_logo
            return Response(
                {
                    "id": str(settings_obj.id) if settings_obj else None,
                    "store_logo": logo_url,
                    "updated_at": settings_obj.updated_at if settings_obj else None,
                },
                status=status.HTTP_200_OK,
            )
        except (ProgrammingError, OperationalError, DatabaseError):
            # Retorno seguro mientras la tabla termina de crearse en PostgreSQL.
            return Response({"store_logo": None}, status=status.HTTP_200_OK)


    def patch(self, request):
        settings_obj, error = _get_or_create_settings(request, create=True)
        if error:
            return error
        serializer = StoreSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class StoreLogoAPIView(APIView):
    """POST /api/v1/store/logo/  DELETE /api/v1/store/logo/"""

    permission_classes = [IsAuthenticated, IsStaffWriteOrPublicRead]

    def post(self, request):
        settings_obj, error = _get_or_create_settings(request, create=True)
        if error:
            return error
        logo = request.data.get("store_logo", "")
        if logo is None:
            logo = ""
        serializer = StoreSettingsSerializer(
            settings_obj, data={"store_logo": logo}, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request):
        settings_obj, error = _get_or_create_settings(request, create=True)
        if error:
            return error
        settings_obj.store_logo = ""
        settings_obj.save(update_fields=["store_logo", "updated_at"])
        return Response(StoreSettingsSerializer(settings_obj).data)
