"""La convocatoria de un partido finalizado se puede corregir con permiso."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import Match, MatchLineup, Player, Team, Tournament


class FinishedMatchRosterTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org Planilla", slug="org-planilla")
        expires = timezone.now() + timedelta(days=30)
        self.owner = User.objects.create_user(
            email="owner-planilla@test.com",
            username="owner_planilla",
            password="SecurePass123!",
            organization=self.org,
            role="manager",
            sports_module_active=True,
            sports_module_expires_at=expires,
        )
        self.outsider = User.objects.create_user(
            email="outsider-planilla@test.com",
            username="outsider_planilla",
            password="SecurePass123!",
            organization=self.org,
            role="user",
        )
        self.level2 = User.objects.create_user(
            email="l2-planilla@test.com",
            username="l2_planilla",
            password="SecurePass123!",
            role="admin",
            admin_level=2,
        )
        self.tournament = Tournament.objects.create(
            name="Copa Planilla",
            slug="copa-planilla",
            sport_type="football",
            organization=self.org,
            posted_by=self.owner,
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        self.home = Team.objects.create(
            name="Local Planilla",
            slug="local-planilla",
            abbreviation="LOP",
            tournament=self.tournament,
            organization=self.org,
            posted_by=self.owner,
        )
        self.away = Team.objects.create(
            name="Visita Planilla",
            slug="visita-planilla",
            abbreviation="VIP",
            tournament=self.tournament,
            organization=self.org,
            posted_by=self.owner,
        )
        self.players = [
            Player.objects.create(
                first_name=f"Jugador{index}",
                last_name="Local",
                jersey_number=index,
                position="forward",
                posted_by=self.owner,
                team=self.home,
                tournament=self.tournament,
            )
            for index in range(1, 7)
        ]
        self.extra = Player.objects.create(
            first_name="Suplente",
            last_name="Extra",
            jersey_number=20,
            position="midfielder",
            posted_by=self.owner,
            team=self.home,
            tournament=self.tournament,
        )
        self.match = Match.objects.create(
            tournament=self.tournament,
            posted_by=self.owner,
            home_team=self.home,
            away_team=self.away,
            match_date=timezone.now(),
            status="finished",
            home_score=1,
            away_score=0,
        )
        self.client = APIClient()

    def _payload(self, players=None):
        chosen = players if players is not None else self.players
        return {
            "team": str(self.home.id),
            "players": [
                {
                    "player": str(player.id),
                    "is_starter": True,
                    "position": player.position,
                    "jersey_number": player.jersey_number,
                }
                for player in chosen
            ],
        }

    def test_owner_can_set_roster_on_finished_match(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            f"/api/v1/sports/matches/{self.match.id}/roster/",
            self._payload(),
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(
            MatchLineup.objects.filter(match=self.match, team=self.home, is_starter=True).count(),
            6,
        )
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, "finished")

    def test_owner_can_remove_a_player_added_by_mistake(self):
        for player in self.players:
            MatchLineup.objects.create(
                match=self.match,
                team=self.home,
                player=player,
                posted_by=self.owner,
                is_starter=True,
                is_on_field=True,
                jersey_number=player.jersey_number,
                position=player.position,
            )
        mistaken = MatchLineup.objects.create(
            match=self.match,
            team=self.home,
            player=self.extra,
            posted_by=self.owner,
            is_starter=False,
            is_on_field=False,
            jersey_number=20,
            position="midfielder",
        )
        self.client.force_authenticate(user=self.owner)
        res = self.client.put(
            f"/api/v1/sports/matches/{self.match.id}/roster/",
            self._payload(),
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertFalse(MatchLineup.objects.filter(pk=mistaken.pk).exists())
        self.assertEqual(MatchLineup.objects.filter(match=self.match, team=self.home).count(), 6)

    def test_owner_can_clear_finished_roster(self):
        MatchLineup.objects.create(
            match=self.match,
            team=self.home,
            player=self.players[0],
            posted_by=self.owner,
            is_starter=True,
        )
        self.client.force_authenticate(user=self.level2)
        res = self.client.delete(
            f"/api/v1/sports/matches/{self.match.id}/roster/?team={self.home.id}"
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["deleted"], 1)
        self.assertFalse(MatchLineup.objects.filter(match=self.match, team=self.home).exists())

    def test_outsider_cannot_edit_finished_roster(self):
        self.client.force_authenticate(user=self.outsider)
        res = self.client.post(
            f"/api/v1/sports/matches/{self.match.id}/roster/",
            self._payload(),
            format="json",
        )
        self.assertEqual(res.status_code, 403, res.content)

    def test_live_match_roster_stays_blocked(self):
        self.match.status = "live"
        self.match.save(update_fields=["status"])
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            f"/api/v1/sports/matches/{self.match.id}/set_lineup/",
            self._payload(),
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
