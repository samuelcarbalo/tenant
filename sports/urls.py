from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TournamentViewSet, TeamViewSet, PlayerViewSet, MatchViewSet

router = DefaultRouter()
router.register(r"tournaments", TournamentViewSet, basename="tournament")
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"players", PlayerViewSet, basename="player")
router.register(r"matches", MatchViewSet, basename="match")

urlpatterns = [
    path("", include(router.urls)),
]
