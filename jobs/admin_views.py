"""Endpoints de administración para historial analítico de vacantes."""

from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import BasePermission, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from core.pagination import StandardResultsSetPagination
from core.permissions import user_is_platform_elevated

from .models import JobOfferHistory
from .serializers import JobOfferHistorySerializer


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if user_is_platform_elevated(user):
            return True
        return bool(getattr(user, "is_staff", False))


class JobOfferHistoryListView(ListAPIView):
    """
    GET /api/v1/admin/jobs/history/
    Historial consolidado de vacantes (activas y depuradas) para analítica.
    """

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = JobOfferHistorySerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_external", "is_purged"]
    search_fields = ["title", "company_name", "published_by__email", "published_by__first_name"]
    ordering_fields = ["created_at", "expired_at", "total_applications_count", "recorded_at"]
    ordering = ["-created_at"]
    queryset = JobOfferHistory.objects.select_related("published_by").all()
