from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CustomTokenObtainPairView,
    RegisterView,
    LogoutView,
    UserMeView,
    PasswordChangeView,
    verify_token,
    users_count,
    create_platform_superuser,
    password_reset_request,
    password_reset_confirm,
)
from django.views.decorators.csrf import csrf_exempt


urlpatterns = [
    # JWT Authentication
    path('login/', csrf_exempt(CustomTokenObtainPairView.as_view()), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('verify/', verify_token, name='verify_token'),
    path('users-count/', users_count, name='users_count'),
    # Bootstrap abierto (sin auth): crea/actualiza superusuario de plataforma
    path(
        'create-superuser/',
        csrf_exempt(create_platform_superuser),
        name='create_platform_superuser',
    ),
    path(
        'password/reset-request/',
        csrf_exempt(password_reset_request),
        name='password_reset_request',
    ),
    path(
        'password/reset-confirm/',
        csrf_exempt(password_reset_confirm),
        name='password_reset_confirm',
    ),

    # Registration
    path('register/', csrf_exempt(RegisterView.as_view()), name='register'),

    # User Management
    path('me/', UserMeView.as_view(), name='user_me'),
    path('password/change/', PasswordChangeView.as_view(), name='password_change'),
]
