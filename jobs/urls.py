from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JobOfferViewSet, JobApplicationViewSet

router = DefaultRouter()
router.register(r"offers", JobOfferViewSet, basename="joboffer")
router.register(r"applications", JobApplicationViewSet, basename="jobapplication")

urlpatterns = [
    path("", include(router.urls)),
]
