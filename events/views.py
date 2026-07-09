from django.db.models import F
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from authentication.models import User
from django.db import transaction
from payments.advertising_packages import CREDIT_COST_EVENT

from .models import EventListing
from .permissions import IsManagerOfOrganization
from .serializers import (
    EventListingCreateUpdateSerializer,
    EventListingDetailSerializer,
    EventListingListSerializer,
)


class EventListingViewSet(viewsets.ModelViewSet):
    queryset = EventListing.objects.select_related("organization", "posted_by")
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["event_category", "is_online", "is_active"]
    search_fields = ["title", "description", "location", "organizer_name"]
    ordering_fields = ["start_datetime", "posted_at", "views_count"]
    ordering = ["start_datetime"]

    def get_serializer_class(self):
        if self.action == "list":
            return EventListingListSerializer
        if self.action in ["create", "update", "partial_update"]:
            return EventListingCreateUpdateSerializer
        return EventListingDetailSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        if self.action in ["create", "update", "partial_update", "destroy", "my_events"]:
            return [IsAuthenticated(), IsManagerOfOrganization()]
        return [AllowAny()]

    def get_queryset(self):
        qs = super().get_queryset()
        my_events = self.request.query_params.get("my_events", "false")
        if (
            self.request.user.is_authenticated
            and my_events.lower() == "true"
            and self.request.user.role in ("manager", "admin")
        ):
            return qs.filter(posted_by=self.request.user)

        return qs.filter(
            is_active=True,
            expires_at__gt=timezone.now(),
            moderation_status="approved",
        )

    def perform_create(self, serializer):
        user = self.request.user
        organizer = (
            serializer.validated_data.get("organizer_name")
            or user.company_name
            or (user.organization.name if user.organization else user.get_full_name())
        )

        with transaction.atomic():
            fresh_user = User.objects.select_for_update().get(id=user.id)
            if fresh_user.credits < CREDIT_COST_EVENT:
                raise ValidationError(
                    {
                        "detail": (
                            f"Publicar un evento cuesta {CREDIT_COST_EVENT} créditos. "
                            f"Tienes {fresh_user.credits}."
                        )
                    }
                )
            fresh_user.credits -= CREDIT_COST_EVENT
            fresh_user.save(update_fields=["credits"])
            user.credits = fresh_user.credits

            serializer.save(
                organization=user.organization,
                posted_by=user,
                organizer_name=organizer,
            )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        EventListing.objects.filter(pk=instance.pk).update(
            views_count=F("views_count") + 1
        )
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_events(self, request):
        qs = EventListing.objects.filter(posted_by=request.user).order_by(
            "-posted_at"
        )
        serializer = EventListingListSerializer(qs, many=True)
        return Response(serializer.data)
