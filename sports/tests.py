from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from authentication.models import User
from organizations.models import Organization
from .models import Match, MatchEvent, Player, Team, Tournament, PlayerSuspension


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
