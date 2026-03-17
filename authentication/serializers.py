from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.cache import cache

from organizations.models import Organization
from profiles.models import Profile

User = get_user_model()


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

        data["user"] = {
            "id": str(self.user.id),
            "email": self.user.email,
            "username": self.user.username,
            "full_name": self.user.full_name,
            "role": self.user.role,
            # AHORA: string si es empresa, null si no
            "company_name": self.user.company_name if self.user.company_name else False,
            "user_type": self.user.user_type,  # opcional
            "organization": {
                "id": str(self.user.organization.id)
                if self.user.organization
                else None,
                "name": self.user.organization.name if self.user.organization else None,
                "slug": self.user.organization.slug if self.user.organization else None,
            },
        }
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # claims personalizados
        token["email"] = user.email
        token["username"] = user.username

        # claims de organización
        if user.organization:
            token["org_id"] = str(user.organization_id)

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
    organization_slug = serializers.CharField(required=True)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")
        org_slug = data.get("organization_slug")

        print(f"========== VALIDATE ==========")
        print(f"Email: {email}, Org: {org_slug}")

        try:
            user = User.objects.select_related("organization").get(
                email=email, organization__slug=org_slug
            )
            print(f"Usuario: {user.username}")
        except User.DoesNotExist:
            print("No existe")
            raise serializers.ValidationError({"email": "Credenciales inválidas."})

        # Verificar password - FORMA CORRECTA
        if not user.check_password(password):
            print("Password mal")
            raise serializers.ValidationError({"email": "Credenciales inválidas."})

        print("Todo OK")
        data["user"] = user
        return data


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer para datos de usuario.
    """

    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )

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
            "organization",
            "organization_name",
            "is_active",
            "email_verified",
            "date_joined",
            "last_login",
            "company_name",
        ]
        read_only_fields = ["id", "email", "organization", "date_joined"]


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
