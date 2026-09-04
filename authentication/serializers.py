from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.cache import cache

from organizations.models import Organization
from profiles.models import Profile

User = get_user_model()


def auth_user_payload(user) -> dict:
    """
    Contrato de sesión para login / me / verify.
    `role` es el rol de organización (user|manager|admin).
    `hierarchy_role` es Super Admin L1/L2 para el frontend de tienda.
    """
    level = int(getattr(user, "admin_level", 0) or 0)
    hierarchy = getattr(user, "hierarchy_role", None)
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "role": user.role,
        "hierarchy_role": hierarchy,
        "admin_level": level,
        "is_superuser": bool(user.is_superuser),
        "is_staff": bool(user.is_staff),
        "is_super_admin_l1": bool(hierarchy == "SUPER_ADMIN_L1"),
        "is_super_admin_l2": bool(hierarchy == "SUPER_ADMIN_L2"),
        "company_name": user.company_name if user.company_name else None,
        "user_type": user.user_type,
        "credits": user.credits,
        "is_unlimited_credits": bool(user.is_unlimited_credits),
        "sports_module_active": bool(user.sports_module_active),
        "sports_module_expires_at": user.sports_module_expires_at,
        "organization": {
            "id": str(user.organization.id),
            "name": user.organization.name,
            "slug": user.organization.slug,
        }
        if user.organization
        else None,
        "organization_name": user.organization.name if user.organization else None,
    }


def _set_token_claims(token, user):
    token["email"] = user.email
    token["username"] = user.username
    token["role"] = user.role
    token["admin_level"] = int(getattr(user, "admin_level", 0) or 0)
    token["is_superuser"] = bool(user.is_superuser)
    token["hierarchy_role"] = getattr(user, "hierarchy_role", None) or ""
    if user.organization_id:
        token["org_id"] = str(user.organization_id)
        token["organization_id"] = str(user.organization_id)


def issue_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    _set_token_claims(refresh, user)
    access = refresh.access_token
    _set_token_claims(access, user)
    return refresh, access


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer personalizado para obtener tokens JWT con información adicional como la organizacion.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        refresh = self.get_token(self.user)

        if self.user.organization:
            refresh["organization_id"] = str(self.user.organization_id)
            refresh["organization_name"] = self.user.organization.name
            refresh["role"] = self.user.role

        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)

        data["user"] = auth_user_payload(self.user)
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        _set_token_claims(token, user)
        return token


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer para registro de usuarios con organización.
    """

    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    organization_name = serializers.CharField(required=False, allow_blank=True)
    organization_slug = serializers.CharField(required=False, allow_blank=True)
    company_name = serializers.CharField(required=False, allow_blank=True)
    user_type = serializers.ChoiceField(
        choices=User.USER_TYPE_CHOICES, default="person"
    )

    class Meta:
        model = User
        fields = [
            "email",
            "username",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "phone",
            "organization_name",
            "organization_slug",
            "company_name",
            "user_type",
        ]

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Las contraseñas no coinciden."}
            )
        org_name = data.get("organization_name")
        org_slug = data.get("organization_slug")
        if org_slug:
            try:
                org = Organization.objects.get(slug=org_slug, is_active=True)
                data["existing_organization"] = org
            except Organization.DoesNotExist:
                raise serializers.ValidationError(
                    {"organization_slug": "La organización no existe."}
                )
        elif org_name:
            # Verificar si el nombre de la organización ya existe
            if Organization.objects.filter(name=org_name, is_active=True).exists():
                raise serializers.ValidationError(
                    {"organization_name": "El nombre de la organización ya existe."}
                )
        else:
            raise serializers.ValidationError(
                {
                    "organization_name": "Debe proporcionar un nombre o slug de organización."
                }
            )
        return data

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        org_name = validated_data.pop("organization_name", None)
        org_slug = validated_data.pop("organization_slug", None)
        existing_org = validated_data.pop("existing_organization", None)

        # Extraer campos del perfil ANTES del **validated_data
        user_type = validated_data.pop("user_type", "person")
        company_name = validated_data.pop("company_name", None)

        with transaction.atomic():
            if existing_org:
                organization = existing_org
            else:
                from organizations.serializers import OrganizationCreateSerializer

                org_serializer = OrganizationCreateSerializer(
                    data={
                        "name": org_name,
                        "slug": org_slug.lower().replace(" ", "-")
                        if org_slug
                        else None,
                        "description": f"Organización creada por {validated_data['email']}",
                    }
                )
                org_serializer.is_valid(raise_exception=True)
                organization = org_serializer.save()

            # IMPORTANTE: Agregar los campos extra al validated_data antes de create_user
            validated_data["user_type"] = user_type
            validated_data["company_name"] = (
                company_name if user_type == "company" else None
            )
            if user_type == "company":
                validated_data["role"] = "manager"
                validated_data["credits"] = 50

            # Crear usuario - ahora sí llegan los campos
            user = User.objects.create_user(
                organization=organization,
                **validated_data,
            )

            # Crear perfil
            Profile.objects.create(
                user=user, organization=organization, dynamic_data={}
            )

            return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    organization_slug = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        from .auth_utils import resolve_login_user

        email = data.get("email")
        password = data.get("password")
        org_slug = (data.get("organization_slug") or "").strip()

        user = resolve_login_user(email, password, org_slug if org_slug else None)

        if not user:
            if org_slug:
                raise serializers.ValidationError({"email": "Credenciales inválidas."})
            raise serializers.ValidationError(
                {
                    "organization_slug": (
                        "Debe indicar el slug de la organización. "
                        "Solo los superusuarios de plataforma pueden iniciar sesión sin organización."
                    )
                }
            )

        data["user"] = user
        return data


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer para datos de usuario.
    """

    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    hierarchy_role = serializers.SerializerMethodField()
    is_super_admin_l1 = serializers.SerializerMethodField()
    is_super_admin_l2 = serializers.SerializerMethodField()

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
            "hierarchy_role",
            "admin_level",
            "organization",
            "organization_name",
            "is_active",
            "is_superuser",
            "is_staff",
            "is_super_admin_l1",
            "is_super_admin_l2",
            "is_unlimited_credits",
            "email_verified",
            "date_joined",
            "last_login",
            "company_name",
            "credits",
            "sports_module_active",
            "sports_module_expires_at",
            "user_type",
        ]
        read_only_fields = [
            "id",
            "email",
            "organization",
            "date_joined",
            "is_superuser",
            "is_staff",
            "admin_level",
            "hierarchy_role",
            "is_super_admin_l1",
            "is_super_admin_l2",
            "sports_module_active",
            "sports_module_expires_at",
        ]

    def get_hierarchy_role(self, obj):
        return getattr(obj, "hierarchy_role", None)

    def get_is_super_admin_l1(self, obj):
        return bool(getattr(obj, "hierarchy_role", None) == "SUPER_ADMIN_L1")

    def get_is_super_admin_l2(self, obj):
        return bool(getattr(obj, "hierarchy_role", None) == "SUPER_ADMIN_L2")

    def to_representation(self, instance):
        from authentication.sports_subscription import sync_sports_module_status

        sync_sports_module_status(instance)
        data = super().to_representation(instance)
        data["id"] = str(instance.id)
        data["admin_level"] = int(getattr(instance, "admin_level", 0) or 0)
        data["is_superuser"] = bool(instance.is_superuser)
        data["is_staff"] = bool(instance.is_staff)
        return data


class PasswordChangeSerializer(serializers.Serializer):  # Cambia a Serializer
    """
    Cambio de contraseña.
    """

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Las contraseñas no coinciden."}
            )
        return data

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Contraseña actual incorrecta.")
        return value

    # No necesitas create() porque no creas un objeto
    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Las contraseñas no coinciden."}
            )
        from authentication.emails import token_generator, user_from_uidb64

        user = user_from_uidb64(data["uid"])
        if user is None or not token_generator.check_token(user, data["token"]):
            raise serializers.ValidationError(
                {"token": "El enlace de restablecimiento no es válido o ya expiró."}
            )
        data["user"] = user
        return data
