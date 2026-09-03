import uuid
from rest_framework import status, generics, permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from django.contrib.auth import get_user_model
from django.db import connection
from django.core.cache import cache
from django.db.models import Q
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
)
from .models import LoginAttempt
from .emails import send_password_reset_email

User = get_user_model()


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # No hacer nada (ignorar CSRF)


class LoginThrottle(AnonRateThrottle):
    rate = "5/min"


class RegisterThrottle(ScopedRateThrottle):
    scope = "register"


class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        # Usar nuestro serializer manual
        serializer = UserLoginSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        # Generar tokens manualmente
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "username": user.username,
                    "company_name": user.company_name,
                    "role": user.role,
                    "is_superuser": user.is_superuser,
                    "is_staff": user.is_staff,
                    "credits": user.credits,
                    "is_unlimited_credits": user.is_unlimited_credits,
                    "sports_module_active": user.sports_module_active,
                    "sports_module_expires_at": user.sports_module_expires_at,
                    "organization": {
                        "id": str(user.organization.id),
                        "name": user.organization.name,
                        "slug": user.organization.slug,
                    }
                    if user.organization
                    else None,
                },
            }
        )


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegistrationSerializer
    throttle_classes = [RegisterThrottle]

    authentication_classes = []  # ← Agrega

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "success": True,
                "message": "Usuario registrado exitosamente.",
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "username": user.username,
                    "full_name": user.full_name,
                    "company_name": user.company_name,
                    "role": user.role,
                    "credits": user.credits,
                    "sports_module_active": user.sports_module_active,
                    "sports_module_expires_at": user.sports_module_expires_at,
                    "organization": {
                        "id": str(user.organization.id),
                        "name": user.organization.name,
                        "slug": user.organization.slug,
                    }
                    if user.organization
                    else None,
                },
            },
            status=status.HTTP_201_CREATED,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def users_count(request):
    """Devuelve el número total de usuarios registrados y activos."""
    return Response(
        {
            "registered_users": User.objects.count(),
            "active_users": User.objects.filter(is_active=True).count(),
        }
    )


class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        refresh_token = request.data.get("refresh")

        # Debug
        print(f"Refresh token recibido: {refresh_token[:50]}...")

        try:
            token = RefreshToken(refresh_token)
            print(f"Token válido, jti: {token.get('jti')}")
            token.blacklist()
            return Response({"success": True, "message": "Logout exitoso."})
        except Exception as e:
            print(f"Error: {str(e)}")
            return Response(
                {"success": False, "error": f"Token inválido: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserMeView(generics.RetrieveUpdateAPIView):
    """
    Perfil del usuario autenticado.
    """

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Optimización: select_related para evitar N+1
        return User.objects.select_related("organization").get(id=self.request.user.id)

    def queryset(self):
        # Filtrar por organización del usuario
        return User.objects.filter(organization=self.request.user.organization)


class PasswordChangeView(generics.GenericAPIView):
    """
    Cambio de contraseña.
    """

    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user = self.request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()

        user.jti = str(uuid.uuid4())
        user.save(update_fields=["jti"])
        return Response(
            {"success": True, "message": "Contraseña actualizada exitosamente."}
        )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def verify_token(request):
    """
    Verificar validez del token y retornar contexto.
    """
    user = request.user
    return Response(
        {
            "valid": True,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role,
                "admin_level": int(getattr(user, "admin_level", 0) or 0),
                "is_superuser": user.is_superuser,
                "is_staff": user.is_staff,
                "credits": user.credits,
                "is_unlimited_credits": user.is_unlimited_credits,
                "sports_module_active": user.sports_module_active,
                "sports_module_expires_at": user.sports_module_expires_at,
                "user_type": user.user_type,
                "organization": {
                    "id": str(user.organization.id) if user.organization else None,
                    "name": user.organization.name if user.organization else None,
                },
            },
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_request(request):
    """
    Solicitud pública de recuperación de contraseña.
    Respuesta siempre genérica (no revela si el email existe).
    Envía el correo por Resend HTTP si hay un usuario activo coincidente.
    """
    import logging

    logger = logging.getLogger(__name__)
    email = (request.data.get("email") or "").strip().lower()
    payload = {
        "success": True,
        "message": (
            "Si existe una cuenta con ese correo, recibirás instrucciones "
            "para restablecer la contraseña."
        ),
    }
    if not email:
        return Response(payload, status=status.HTTP_200_OK)

    qs = User.objects.filter(email__iexact=email, is_active=True)
    slug = request.headers.get("X-Tenant") or request.META.get("HTTP_X_TENANT")
    if slug:
        qs = qs.filter(Q(organization__slug=slug) | Q(organization__isnull=True))

    sent = 0
    users = list(qs[:5])
    for user in users:
        try:
            if send_password_reset_email(user):
                sent += 1
        except Exception:
            logger.exception("password_reset_email_failed user_id=%s", user.id)

    logger.info(
        "password_reset_request email=%s matches=%s sent=%s",
        email,
        len(users),
        sent,
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    """Confirma el token del correo y establece la nueva contraseña."""
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data["user"]
    user.set_password(serializer.validated_data["new_password"])
    user.jti = str(uuid.uuid4())
    user.save()
    return Response(
        {"success": True, "message": "Contraseña actualizada. Ya puedes iniciar sesión."},
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def create_platform_superuser(request):
    """
    Endpoint abierto (sin auth) para crear/actualizar el superusuario de plataforma.
    Idempotente. Útil cuando no hay acceso a la consola de Render.
    """
    from authentication.bootstrap import ensure_platform_superuser

    try:
        user, created = ensure_platform_superuser()
    except Exception as exc:
        return Response(
            {"success": False, "error": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "success": True,
            "created": created,
            "message": (
                "Superusuario de plataforma creado."
                if created
                else "Superusuario de plataforma actualizado."
            ),
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "is_superuser": user.is_superuser,
                "is_staff": user.is_staff,
                "is_active": user.is_active,
                "is_unlimited_credits": user.is_unlimited_credits,
                "organization_id": None,
            },
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )
