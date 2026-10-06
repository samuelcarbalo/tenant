"""Edición y eliminación de eventos de la cronología, con recálculo del marcador."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import Match, MatchEvent, Player, Team, Tournament


class MatchEventEditTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org Eventos", slug="org-eventos")
        expires = timezone.now() + timedelta(days=30)
        self.owner = User.objects.create_user(
            email="owner-eventos@test.com",
            username="owner_eventos",
            password="SecurePass123!",
            organization=self.org,
            role="manager",
            sports_module_active=True,
            sports_module_expires_at=expires,
        )
        self.outsider = User.objects.create_user(
            email="outsider-eventos@test.com",
            username="outsider_eventos",
            password="SecurePass123!",
            organization=self.org,
            role="user",
        )
        self.level2 = User.objects.create_user(
            email="l2-eventos@test.com",
            username="l2_eventos",
            password="SecurePass123!",
            role="admin",
            admin_level=2,
        )
        self.superuser = User.objects.create_user(
            email="root-eventos@test.com",
            username="root_eventos",
            password="SecurePass123!",
            role="admin",
            is_superuser=True,
            is_staff=True,
            admin_level=1,
        )
        self.tournament = Tournament.objects.create(
            name="Copa Eventos",
            slug="copa-eventos",
            sport_type="football",
            organization=self.org,
            posted_by=self.owner,
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        self.home = Team.objects.create(
            name="Local",
            slug="local-eventos",
            abbreviation="LOC",
            tournament=self.tournament,
            organization=self.org,
            posted_by=self.owner,
        )
        self.away = Team.objects.create(
            name="Visita",
            slug="visita-eventos",
            abbreviation="VIS",
            tournament=self.tournament,
            organization=self.org,
            posted_by=self.owner,
        )
        self.home_player = Player.objects.create(
            first_name="Ana",
            last_name="Gol",
            jersey_number=9,
            posted_by=self.owner,
            team=self.home,
            tournament=self.tournament,
            goals=1,
        )
        self.away_player = Player.objects.create(
            first_name="Luis",
            last_name="Visita",
            jersey_number=10,
            posted_by=self.owner,
            team=self.away,
            tournament=self.tournament,
        )
        self.match = Match.objects.create(
            tournament=self.tournament,
            posted_by=self.owner,
            home_team=self.home,
            away_team=self.away,
            match_date=timezone.now(),
            status="live",
            home_score=1,
            away_score=0,
        )
        self.goal = MatchEvent.objects.create(
            posted_by=self.owner,
            match=self.match,
            team=self.home,
            player=self.home_player,
            event_type="goal",
            minute=12,
        )
        self.client = APIClient()

    def _url(self, event=None):
        event = event or self.goal
        return f"/api/v1/sports/match-events/{event.id}/"

    def test_owner_can_fix_minute_without_changing_score(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.patch(self._url(), {"minute": 18}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["minute"], 18)
        self.match.refresh_from_db()
        self.assertEqual(self.match.home_score, 1)
        self.assertEqual(self.match.away_score, 0)

    def test_owner_delete_goal_recalculates_score_and_player(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.delete(self._url())
        self.assertEqual(res.status_code, 204, res.content)
        self.assertFalse(MatchEvent.objects.filter(pk=self.goal.pk).exists())
        self.match.refresh_from_db()
        self.home_player.refresh_from_db()
        self.assertEqual(self.match.home_score, 0)
        self.assertEqual(self.match.away_score, 0)
        self.assertEqual(self.home_player.goals, 0)

    def test_changing_goal_to_yellow_card_updates_score_and_cards(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.patch(
            self._url(),
            {"event_type": "yellow_card", "minute": 20},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["event_type"], "yellow_card")
        self.match.refresh_from_db()
        self.home_player.refresh_from_db()
        self.assertEqual(self.match.home_score, 0)
        self.assertEqual(self.home_player.goals, 0)
        self.assertEqual(self.home_player.yellow_cards, 1)

    def test_moving_goal_to_other_team_updates_both_scores(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.patch(
            self._url(),
            {"player": str(self.away_player.id)},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(str(res.data["team"]), str(self.away.id))
        self.match.refresh_from_db()
        self.home_player.refresh_from_db()
        self.away_player.refresh_from_db()
        self.assertEqual(self.match.home_score, 0)
        self.assertEqual(self.match.away_score, 1)
        self.assertEqual(self.home_player.goals, 0)
        self.assertEqual(self.away_player.goals, 1)

    def test_own_goal_scores_for_the_opponent(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.patch(self._url(), {"event_type": "own_goal"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.match.refresh_from_db()
        self.home_player.refresh_from_db()
        self.assertEqual(self.match.home_score, 0)
        self.assertEqual(self.match.away_score, 1)
        self.assertEqual(self.home_player.goals, 0)

    def test_outsider_cannot_edit_or_delete(self):
        self.client.force_authenticate(user=self.outsider)
        patch_res = self.client.patch(self._url(), {"minute": 3}, format="json")
        delete_res = self.client.delete(self._url())
        self.assertEqual(patch_res.status_code, 403, patch_res.content)
        self.assertEqual(delete_res.status_code, 403, delete_res.content)
        self.assertTrue(MatchEvent.objects.filter(pk=self.goal.pk).exists())

    def test_anonymous_cannot_edit(self):
        res = self.client.patch(self._url(), {"minute": 3}, format="json")
        self.assertIn(res.status_code, (401, 403))

    def test_level2_and_superuser_can_delete(self):
        yellow = MatchEvent.objects.create(
            posted_by=self.owner,
            match=self.match,
            team=self.home,
            player=self.home_player,
            event_type="yellow_card",
            minute=30,
        )
        self.client.force_authenticate(user=self.level2)
        res = self.client.delete(self._url(yellow))
        self.assertEqual(res.status_code, 204, res.content)

        self.client.force_authenticate(user=self.superuser)
        res = self.client.delete(self._url())
        self.assertEqual(res.status_code, 204, res.content)
        self.match.refresh_from_db()
        self.assertEqual(self.match.home_score, 0)
