"""Edición de equipos: Super Admin L1/L2, creador del torneo, delegado y capitán."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import Player, Team, Tournament


class TeamEditRBACTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org Equipos", slug="org-equipos")
        self.other_org = Organization.objects.create(name="Otra Org", slug="otra-org")

        def make_user(username, **extra):
            return User.objects.create_user(
                email=f"{username}@test.com",
                username=username,
                password="SecurePass123!",
                organization=extra.pop("organization", self.org),
                **extra,
            )

        self.owner = make_user(
            "owner_eq",
            role="manager",
            sports_module_expires_at=timezone.now() + timedelta(days=30),
        )
        self.delegate = make_user("delegado_eq", role="user", organization=self.other_org)
        self.captain_user = make_user("capitan_eq", role="user")
        self.member = make_user("miembro_eq", role="manager")
        self.level2 = make_user("l2_eq", admin_level=2)

        self.tournament = Tournament.objects.create(
            name="Copa Equipos",
            slug="copa-equipos",
            sport_type="football",
            organization=self.org,
            posted_by=self.owner,
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        self.other_tournament = Tournament.objects.create(
            name="Otra Copa",
            slug="otra-copa",
            sport_type="football",
            organization=self.org,
            posted_by=self.member,
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        self.team = Team.objects.create(
            name="Club Uno",
            slug="club-uno",
            abbreviation="CU",
            tournament=self.tournament,
            organization=self.org,
            posted_by=self.owner,
            coach_email=self.delegate.email,
        )
        Player.objects.create(
            first_name="Capi",
            last_name="Tán",
            jersey_number=10,
            team=self.team,
            tournament=self.tournament,
            posted_by=self.owner,
            user=self.captain_user,
            is_captain=True,
        )
        self.url = f"/api/v1/sports/teams/{self.team.id}/"

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _patch(self, user, data):
        return self._client(user).patch(self.url, data, format="json")

    def test_allowed_roles_can_edit_team(self):
        payload = {
            "name": "Club Renovado",
            "logo": "https://cdn.test/logo.png",
            "primary_color": "#112233",
            "secondary_color": "#445566",
            "coach_name": "Profe",
        }
        for user in (self.level2, self.owner, self.delegate, self.captain_user):
            res = self._patch(user, payload)
            self.assertEqual(res.status_code, 200, f"{user.username}: {res.content}")
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "Club Renovado")
        self.assertEqual(self.team.primary_color, "#112233")

    def test_patch_by_slug_works_for_delegate(self):
        res = self._client(self.delegate).patch(
            f"/api/v1/sports/teams/{self.team.slug}/?tournament={self.tournament.slug}",
            {"coach_name": "Nuevo DT"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_unrelated_org_member_cannot_edit_team(self):
        res = self._patch(self.member, {"name": "Hackeado"})
        self.assertEqual(res.status_code, 403, res.content)
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "Club Uno")

    def test_non_super_admin_cannot_move_team_to_other_tournament(self):
        res = self._patch(self.delegate, {"tournament": str(self.other_tournament.id)})
        self.assertEqual(res.status_code, 403, res.content)

    def test_captain_cannot_delete_team(self):
        res = self._client(self.captain_user).delete(self.url)
        self.assertEqual(res.status_code, 403, res.content)
        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_can_edit_flag_in_detail(self):
        detail = f"/api/v1/sports/teams/{self.team.id}/"
        self.assertTrue(self._client(self.captain_user).get(detail).json()["can_edit"])
        self.assertFalse(self._client(self.member).get(detail).json()["can_edit"])
        self.assertFalse(APIClient().get(detail).json()["can_edit"])

    def test_only_team_editors_can_add_players(self):
        payload = {
            "first_name": "Nuevo",
            "last_name": "Jugador",
            "jersey_number": 22,
            "position": "forward",
            "team": str(self.team.id),
            "tournament": str(self.tournament.id),
        }
        res = self._client(self.member).post("/api/v1/sports/players/", payload, format="json")
        self.assertEqual(res.status_code, 403, res.content)
        res = self._client(self.captain_user).post("/api/v1/sports/players/", payload, format="json")
        self.assertEqual(res.status_code, 201, res.content)
