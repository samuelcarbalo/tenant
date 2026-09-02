from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from core.pagination import StandardResultsSetPagination
from core.permissions import (
    LEVEL1_FORBIDDEN_MESSAGE,
    IsSuperAdminLevel1,
    user_admin_level,
    user_is_protected_platform_admin,
    user_is_super_admin_l1,
)

User = get_user_model()

L1_IMMUTABLE_MESSAGE = (
    "El Super Admin Root (Nivel 1) no puede ser degradado ni bloqueado."
)


def _forbidden_level1():
    return Response(
        {
            "success": False,
            "detail": LEVEL1_FORBIDDEN_MESSAGE,
            "message": LEVEL1_FORBIDDEN_MESSAGE,
        },
        status=status.HTTP_403_FORBIDDEN,
    )


PANEL_ROLE_CHOICES = (
    ("user", "Usuario estándar"),
    ("manager", "Gestor / Moderador"),
    ("admin", "Administrador Delegado (Nivel 2)"),
    ("super_admin", "Super Administrador Root (Nivel 1)"),
)


def _panel_role_of(user) -> str:
    level = user_admin_level(user)
    if level == User.ADMIN_LEVEL_ROOT:
        return "super_admin"
    if level == User.ADMIN_LEVEL_DELEGATE:
        return "admin"
    if getattr(user, "role", None) == "manager":
        return "manager"
    return "user"


def _hierarchy_from_payload(panel_role, admin_level, instance):
    """Traduce role=super_admin | admin_level=1 a (nivel, role de org)."""
    if admin_level is not None and admin_level != "":
        level = int(admin_level)
        if level == User.ADMIN_LEVEL_ROOT:
            return User.ADMIN_LEVEL_ROOT, "admin"
        if level == User.ADMIN_LEVEL_DELEGATE:
            return User.ADMIN_LEVEL_DELEGATE, "admin"
        org_role = panel_role if panel_role in ("user", "manager") else "user"
        return User.ADMIN_LEVEL_USER, org_role
    if panel_role == "super_admin":
        return User.ADMIN_LEVEL_ROOT, "admin"
    if panel_role == "admin":
        return User.ADMIN_LEVEL_DELEGATE, "admin"
    if panel_role in ("user", "manager"):
        return User.ADMIN_LEVEL_USER, panel_role
    return None, None


def _apply_hierarchy(user, admin_level: int, org_role: str = "user"):
    if admin_level == User.ADMIN_LEVEL_ROOT:
        user.admin_level = User.ADMIN_LEVEL_ROOT
        user.is_staff = True
        user.is_superuser = True
        user.role = "admin"
        user.is_unlimited_credits = True
        user.is_active = True
    elif admin_level == User.ADMIN_LEVEL_DELEGATE:
        user.admin_level = User.ADMIN_LEVEL_DELEGATE
        user.is_staff = True
        user.is_superuser = False
        user.role = "admin"
        user.is_active = True
    else:
        user.admin_level = User.ADMIN_LEVEL_USER
        user.is_staff = False
        user.is_superuser = False
        user.role = org_role if org_role in ("user", "manager") else "user"
    user.save()
    return user


def _apply_promote(user, admin_level: int):
    if (
        user_admin_level(user) == User.ADMIN_LEVEL_ROOT
        and admin_level != User.ADMIN_LEVEL_ROOT
    ):
        return Response(
            {"detail": L1_IMMUTABLE_MESSAGE},
            status=status.HTTP_400_BAD_REQUEST,
        )
    _apply_hierarchy(user, admin_level, org_role="admin")
    return Response(AdminUserSerializer(user).data)


def _apply_demote(user):
    if user_admin_level(user) == User.ADMIN_LEVEL_ROOT:
        return Response(
            {"detail": L1_IMMUTABLE_MESSAGE},
            status=status.HTTP_400_BAD_REQUEST,
        )
    _apply_hierarchy(user, User.ADMIN_LEVEL_USER, org_role="user")
    return Response(AdminUserSerializer(user).data)


class AdminUserSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)
    has_unlimited_credits = serializers.BooleanField(read_only=True)
    admin_level_label = serializers.SerializerMethodField()
    panel_role = serializers.SerializerMethodField()

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
            "panel_role",
            "admin_level",
            "admin_level_label",
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
            "admin_level",
            "admin_level_label",
            "panel_role",
            "date_joined",
            "last_login",
            "has_unlimited_credits",
        ]

    def get_admin_level_label(self, obj):
        level = user_admin_level(obj)
        if level == User.ADMIN_LEVEL_ROOT:
            return "Super Admin Root (Nivel 1)"
        if level == User.ADMIN_LEVEL_DELEGATE:
            return "Administrador (Nivel 2)"
        return ""

    def get_panel_role(self, obj):
        return _panel_role_of(obj)


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=PANEL_ROLE_CHOICES, required=False)
    admin_level = serializers.IntegerField(required=False, min_value=0, max_value=2)

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone",
            "role",
            "admin_level",
            "user_type",
            "company_name",
            "is_active",
            "credits",
            "is_unlimited_credits",
            "email_verified",
        ]

    def update(self, instance, validated_data):
        panel_role = validated_data.pop("role", None)
        req_level = validated_data.pop("admin_level", None)
        instance = super().update(instance, validated_data)
        target_level, org_role = _hierarchy_from_payload(panel_role, req_level, instance)
        if target_level is None:
            return instance
        _apply_hierarchy(instance, target_level, org_role=org_role)
        instance.refresh_from_db()
        return instance


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


class AdminPromoteSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(required=False)
    admin_level = serializers.ChoiceField(
        choices=[User.ADMIN_LEVEL_ROOT, User.ADMIN_LEVEL_DELEGATE],
        default=User.ADMIN_LEVEL_DELEGATE,
    )


class AdminDemoteSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(required=False)


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    CRUD de usuarios para el panel de administración.
    Promover/degradar roles de Super Admin exige Nivel 1.
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = StandardResultsSetPagination
    http_method_names = ["get", "patch", "put", "delete", "post", "head", "options"]

    def get_permissions(self):
        if self.action in ("promote", "demote", "promote_detail", "demote_detail"):
            return [IsAuthenticated(), IsSuperAdminLevel1()]
        return [IsAuthenticated(), IsAdminUser()]

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

    def _resolve_target(self, user_id=None):
        if user_id is None:
            return self.get_object()
        try:
            return self.get_queryset().get(pk=user_id)
        except User.DoesNotExist:
            return None

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
        if user_admin_level(instance) == User.ADMIN_LEVEL_ROOT or instance.is_superuser:
            return Response(
                {"detail": L1_IMMUTABLE_MESSAGE},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user_is_protected_platform_admin(instance) and not user_is_super_admin_l1(
            request.user
        ):
            return _forbidden_level1()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def partial_update(self, request, *args, **kwargs):
        target = self.get_object()
        actor = request.user
        incoming_role = request.data.get("role", serializers.empty)
        incoming_level = request.data.get("admin_level", serializers.empty)
        incoming_active = request.data.get("is_active", serializers.empty)

        requested_level = None
        if incoming_level not in (serializers.empty, None, ""):
            try:
                requested_level = int(incoming_level)
            except (TypeError, ValueError):
                requested_level = None
        elif incoming_role is not serializers.empty:
            mapped, _org = _hierarchy_from_payload(incoming_role, None, target)
            requested_level = mapped

        if requested_level in (
            User.ADMIN_LEVEL_ROOT,
            User.ADMIN_LEVEL_DELEGATE,
        ) and not user_is_super_admin_l1(actor):
            return _forbidden_level1()
        if incoming_role == "super_admin" and not user_is_super_admin_l1(actor):
            return _forbidden_level1()

        if user_admin_level(target) == User.ADMIN_LEVEL_ROOT:
            if incoming_active is not serializers.empty and str(
                incoming_active
            ).lower() in ("false", "0"):
                if not user_is_super_admin_l1(actor):
                    return _forbidden_level1()
                return Response(
                    {"detail": L1_IMMUTABLE_MESSAGE},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if requested_level is not None and requested_level != User.ADMIN_LEVEL_ROOT:
                if not user_is_super_admin_l1(actor):
                    return _forbidden_level1()
                return Response(
                    {"detail": L1_IMMUTABLE_MESSAGE},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if (
                incoming_role is not serializers.empty
                and incoming_role != "super_admin"
                and _panel_role_of(target) == "super_admin"
            ):
                if not user_is_super_admin_l1(actor):
                    return _forbidden_level1()
                return Response(
                    {"detail": L1_IMMUTABLE_MESSAGE},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if not user_is_super_admin_l1(actor):
            if user_is_protected_platform_admin(target):
                return _forbidden_level1()
            if incoming_role in ("admin", "super_admin"):
                return _forbidden_level1()

        response = super().partial_update(request, *args, **kwargs)
        if getattr(response, "status_code", 0) == status.HTTP_200_OK:
            return Response(AdminUserSerializer(self.get_object()).data)
        return response

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = kwargs.get("partial", False)
        if not kwargs["partial"]:
            return self.partial_update(request, *args, **kwargs)
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="credits")
    def set_credits(self, request, pk=None):
        user = self.get_object()
        if user_is_protected_platform_admin(user) and not user_is_super_admin_l1(
            request.user
        ):
            return _forbidden_level1()
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
        making_inactive = not serializer.validated_data["is_active"]
        if user.pk == request.user.pk and making_inactive:
            return Response(
                {"detail": "No puedes desactivar tu propia cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user_admin_level(user) == User.ADMIN_LEVEL_ROOT and making_inactive:
            if not user_is_super_admin_l1(request.user):
                return _forbidden_level1()
            return Response(
                {"detail": L1_IMMUTABLE_MESSAGE},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user_is_protected_platform_admin(user) and not user_is_super_admin_l1(
            request.user
        ):
            return _forbidden_level1()
        user.is_active = serializer.validated_data["is_active"]
        user.save(update_fields=["is_active", "updated_at"])
        return Response(AdminUserSerializer(user).data)

    @action(
        detail=False,
        methods=["post"],
        url_path="promote",
        permission_classes=[IsAuthenticated, IsSuperAdminLevel1],
    )
    def promote(self, request):
        serializer = AdminPromoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data.get("user_id")
        if not user_id:
            return Response(
                {"detail": "Indica user_id del usuario a ascender."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target = self._resolve_target(user_id)
        if target is None:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if target.pk == request.user.pk:
            return Response(
                {"detail": "No puedes cambiar tu propio nivel de administrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _apply_promote(target, serializer.validated_data["admin_level"])

    @action(
        detail=False,
        methods=["post"],
        url_path="demote",
        permission_classes=[IsAuthenticated, IsSuperAdminLevel1],
    )
    def demote(self, request):
        serializer = AdminDemoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data.get("user_id")
        if not user_id:
            return Response(
                {"detail": "Indica user_id del usuario a degradar."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target = self._resolve_target(user_id)
        if target is None:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if target.pk == request.user.pk:
            return Response(
                {"detail": "No puedes degradar tu propia cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _apply_demote(target)

    @action(
        detail=True,
        methods=["post"],
        url_path="promote",
        permission_classes=[IsAuthenticated, IsSuperAdminLevel1],
    )
    def promote_detail(self, request, pk=None):
        target = self.get_object()
        serializer = AdminPromoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if target.pk == request.user.pk:
            return Response(
                {"detail": "No puedes cambiar tu propio nivel de administrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _apply_promote(target, serializer.validated_data["admin_level"])

    @action(
        detail=True,
        methods=["post"],
        url_path="demote",
        permission_classes=[IsAuthenticated, IsSuperAdminLevel1],
    )
    def demote_detail(self, request, pk=None):
        target = self.get_object()
        if target.pk == request.user.pk:
            return Response(
                {"detail": "No puedes degradar tu propia cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _apply_demote(target)
