from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    CustomTokenObtainPairView,
    RegisterView,
    LogoutView,
    UserMeView,
    PasswordChangeView,
    verify_token
)
from django.views.decorators.csrf import csrf_exempt


urlpatterns = [
    # JWT Authentication
    path('login/', csrf_exempt(CustomTokenObtainPairView.as_view()), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('verify/', verify_token, name='verify_token'),
    
    # Registration
    path('register/', csrf_exempt(RegisterView.as_view()), name='register'),
    
    # User Management
    path('me/', UserMeView.as_view(), name='user_me'),
    path('password/change/', PasswordChangeView.as_view(), name='password_change'),
]
