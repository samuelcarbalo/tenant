from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from authentication.models import User
from organizations.models import Organization
from profiles.models import Profile
from .models import Match, MatchEvent, Player, Team, Tournament, PlayerSuspension
from .services.suspensions import is_player_suspended_for_match, process_suspensions_on_match_finish
from .views import MatchViewSet, PlayerViewSet
from rest_framework.test import APIRequestFactory


class SportsSanctionsTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Test Org",
            slug="test-org",
            description="",
        )
        self.user = User.objects.create_user(
            email="admin@example.com",
            username="admin",
            password="secret123",
            organization=self.organization,
            role="admin",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            slug="test-tournament",
            description="",
            posted_by=self.user,
            organization=self.organization,
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            registration_deadline=timezone.now().date(),
        )
        self.team = Team.objects.create(
            name="Test Team",
            slug="test-team",
            abbreviation="TT",
            description="",
            posted_by=self.user,
            tournament=self.tournament,
            organization=self.organization,
        )
        self.player = Player.objects.create(
            first_name="Juan",
            last_name="Perez",
            id_number="123456789",
            email="juan@example.com",
            posted_by=self.user,
            team=self.team,
            tournament=self.tournament,
        )
        self.match = Match.objects.create(
            tournament=self.tournament,
            home_team=self.team,
            away_team=self.team,
            home_score=0,
            away_score=0,
            match_date=timezone.now().date(),
            posted_by=self.user,
            venue="Test",
        )

    def test_second_yellow_becomes_red_and_creates_suspension(self):
        from .views import MatchViewSet

        first_event = MatchEvent.objects.create(
            posted_by=self.user,
            match=self.match,
            team=self.team,
            player=self.player,
            event_type="yellow_card",
            minute=10,
            description="Primera amarilla",
        )
        viewset = MatchViewSet()
        viewset._handle_player_card_event(first_event)

        second_event = MatchEvent.objects.create(
            posted_by=self.user,
            match=self.match,
            team=self.team,
            player=self.player,
            event_type="yellow_card",
            minute=42,
            description="Segunda amarilla",
        )
        viewset._handle_player_card_event(second_event)

        self.player.refresh_from_db()
        self.assertEqual(self.player.yellow_cards, 1)
        self.assertEqual(self.player.red_cards, 1)
        self.assertTrue(PlayerSuspension.objects.filter(player=self.player, tournament=self.tournament).exists())

    def test_multi_match_manual_suspension_blocks_lineup(self):
        away_team = Team.objects.create(
            name="Away Team",
            slug="away-team",
            abbreviation="AT",
            description="",
            posted_by=self.user,
            tournament=self.tournament,
            organization=self.organization,
        )
        next_match = Match.objects.create(
            tournament=self.tournament,
            home_team=self.team,
            away_team=away_team,
            home_score=0,
            away_score=0,
            match_date=timezone.now().date() + timezone.timedelta(days=1),
            posted_by=self.user,
            venue="Test 2",
        )
        suspension = PlayerSuspension.objects.create(
            player=self.player,
            tournament=self.tournament,
            match=self.match,
            reason="manual",
            matches_count=2,
            matches_served=0,
            notes="Sanción manual de prueba",
            created_by=self.user,
            is_active=True,
            suspended_until_match=next_match,
        )
        self.assertTrue(is_player_suspended_for_match(self.player, next_match)[0])

        next_match.status = "finished"
        next_match.save(update_fields=["status"])
        process_suspensions_on_match_finish(next_match)

        suspension.refresh_from_db()
        self.assertEqual(suspension.matches_served, 1)
        self.assertTrue(suspension.is_active)

    def test_player_create_auto_user_with_profile(self):
        factory = APIRequestFactory()
        request = factory.post("/api/v1/sports/players/")
        request.user = self.user

        view = PlayerViewSet()
        view.request = request
        from .serializers import PlayerCreateUpdateSerializer

        serializer = PlayerCreateUpdateSerializer(data={
            "first_name": "Pedro",
            "last_name": "Lopez",
            "email": "pedro@example.com",
            "id_number": "99887766",
            "team": str(self.team.id),
            "tournament": str(self.tournament.id),
            "position": "forward",
        })
        serializer.is_valid(raise_exception=True)
        view.perform_create(serializer)

        player = Player.objects.get(email="pedro@example.com")
        self.assertIsNotNone(player.user)
        self.assertTrue(
            Profile.objects.filter(user=player.user, organization=self.organization).exists()
        )
        self.assertEqual(User.objects.filter(email="pedro@example.com").count(), 1)
