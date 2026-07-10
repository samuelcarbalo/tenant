from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TournamentViewSet,
    TeamViewSet,
    PlayerViewSet,
    MatchViewSet,
    AdvertisementBannerViewSet,
    PlayerSuspensionViewSet,
)

router = DefaultRouter()
router.register(r"tournaments", TournamentViewSet, basename="tournament")
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"players", PlayerViewSet, basename="player")
router.register(r"matches", MatchViewSet, basename="match")
router.register(r"banners", AdvertisementBannerViewSet, basename="banners")
router.register(r"player-suspensions", PlayerSuspensionViewSet, basename="player-suspension")
urlpatterns = [
    path("", include(router.urls)),
]
