from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClassifiedAdCampaignViewSet, TournamentSponsorshipViewSet

router = DefaultRouter()
router.register(
    r"sponsorships", TournamentSponsorshipViewSet, basename="tournament-sponsorship"
)
router.register(r"campaigns", ClassifiedAdCampaignViewSet, basename="ad-campaign")

urlpatterns = [
    path("", include(router.urls)),
]
