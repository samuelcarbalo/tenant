from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EventListingViewSet

router = DefaultRouter()
router.register(r"listings", EventListingViewSet, basename="event-listing")

urlpatterns = [
    path("", include(router.urls)),
]
