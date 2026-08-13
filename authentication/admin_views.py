from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from core.pagination import StandardResultsSetPagination

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)
    has_unlimited_credits = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone",
            "full_name",
            "role",
            "user_type",
            "company_name",
            "organization",
            "organization_name",
            "organization_slug",
            "is_active",
            "is_staff",
            "is_superuser",
            "is_unlimited_credits",
            "has_unlimited_credits",
            "credits",
            "email_verified",
            "date_joined",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "email",
            "organization",
            "is_superuser",
            "is_staff",
            "date_joined",
            "last_login",
            "has_unlimited_credits",
        ]


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone",
            "role",
            "user_type",
            "company_name",
            "is_active",
            "credits",
            "is_unlimited_credits",
            "email_verified",
        ]


class AdminCreditsSerializer(serializers.Serializer):
    credits = serializers.IntegerField(min_value=0, required=False)
    delta = serializers.IntegerField(required=False)
    is_unlimited_credits = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if (
            attrs.get("credits") is None
            and attrs.get("delta") is None
            and attrs.get("is_unlimited_credits") is None
        ):
            raise serializers.ValidationError(
                "Indica credits, delta o is_unlimited_credits."
            )
        return attrs


class AdminActiveSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    CRUD de usuarios para superadministradores (is_staff / IsAdminUser).
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = StandardResultsSetPagination
    http_method_names = ["get", "patch", "put", "delete", "post", "head", "options"]

    def get_queryset(self):
        qs = User.objects.select_related("organization").order_by("-date_joined")
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        active = self.request.query_params.get("is_active")
        if active in ("true", "false"):
            qs = qs.filter(is_active=active == "true")
        return qs

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "El alta de usuarios se hace por registro público."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.pk == request.user.pk:
            return Response(
                {"detail": "No puedes eliminar tu propia cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if instance.is_superuser:
            return Response(
                {"detail": "No se pueden eliminar superusuarios desde este panel."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="credits")
    def set_credits(self, request, pk=None):
        user = self.get_object()
        serializer = AdminCreditsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("credits") is not None:
            user.credits = data["credits"]
        if data.get("delta") is not None:
            user.credits = max(0, user.credits + data["delta"])
        if data.get("is_unlimited_credits") is not None:
            user.is_unlimited_credits = data["is_unlimited_credits"]
        user.save()
        return Response(AdminUserSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        user = self.get_object()
        serializer = AdminActiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if user.pk == request.user.pk and not serializer.validated_data["is_active"]:
            return Response(
                {"detail": "No puedes desactivar tu propia cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.is_active = serializer.validated_data["is_active"]
        user.save(update_fields=["is_active", "updated_at"])
        return Response(AdminUserSerializer(user).data)
