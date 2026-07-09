from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RealEstateOfferViewSet

router = DefaultRouter()
router.register(r"offers", RealEstateOfferViewSet, basename="realestateoffer")

urlpatterns = [
    path("", include(router.urls)),
]
