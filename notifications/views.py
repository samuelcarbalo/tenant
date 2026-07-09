from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer, NotificationCreateSerializer
from .services import create_notification


class NotificationViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    lookup_field = "pk"

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")

    def list(self, request):
        unread_only = request.query_params.get("unread") == "true"
        qs = self.get_queryset()
        if unread_only:
            qs = qs.filter(read_at__isnull=True)
        page = self.paginate_queryset(qs)
        serializer = NotificationSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request):
        serializer = NotificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        notification = create_notification(
            user=request.user,
            notification_type=data["type"],
            message=data["message"],
            extra_data=data.get("extra_data", {}),
        )
        return Response(NotificationSerializer(notification).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notification = self.get_queryset().filter(pk=pk).first()
        if not notification:
            return Response({"error": "No encontrada."}, status=status.HTTP_404_NOT_FOUND)
        notification.mark_read()
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"success": True, "marked": updated})

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = self.get_queryset().filter(read_at__isnull=True).count()
        return Response({"unread_count": count})
