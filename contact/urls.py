from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ContactMessageViewSet

router = DefaultRouter()
router.register(r"messages", ContactMessageViewSet, basename="contact-message")

urlpatterns = [
    path("", include(router.urls)),
]
