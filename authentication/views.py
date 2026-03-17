import uuid
from rest_framework import status, generics, permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from django.contrib.auth import get_user_model
from django.db import connection
from django.core.cache import cache
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserSerializer,
    PasswordChangeSerializer,
)
from .models import LoginAttempt

User = get_user_model()


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # No hacer nada (ignorar CSRF)


class LoginThrottle(AnonRateThrottle):
    rate = "5/min"


class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    authentication_classes = []

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
    throttle_classes = [AnonRateThrottle]

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
                "organization": {
                    "id": str(user.organization.id) if user.organization else None,
                    "name": user.organization.name if user.organization else None,
                },
            },
        }
    )
