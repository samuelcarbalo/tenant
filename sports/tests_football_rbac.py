from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.formats.templates import get_template
from sports.models import Player, Team, Tournament
from sports.services.advancement import resolve_team_source
from sports.services.structure import apply_format_template


class FootballTournamentCreationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name="Chever Org", slug="chever-org")
        expires = timezone.now() + timedelta(days=30)
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            password="secret123",
            organization=self.org,
            role="manager",
            sports_module_active=True,
            sports_module_expires_at=expires,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)
        self.today = timezone.now().date()

    def _payload(self, **overrides):
        data = {
            "name": "Copa Chever Fútbol",
            "slug": "copa-chever-futbol",
            "description": "Torneo de prueba",
            "sport_type": "football",
            "category": "sub-17",
            "start_date": str(self.today + timedelta(days=14)),
            "end_date": str(self.today + timedelta(days=60)),
            "registration_deadline": str(self.today + timedelta(days=7)),
            "max_teams": 8,
            "min_players_per_team": 7,
            "max_players_per_team": 22,
            "format_template": "round_robin_single",
        }
        data.update(overrides)
        return data

    def test_create_football_tournament_initializes_params_and_is_active(self):
        res = self.client.post(
            "/api/v1/sports/tournaments/",
            self._payload(),
            format="json",
            HTTP_X_TENANT="chever-org",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["sport_type"], "football")
        self.assertEqual(res.data["category"], "sub-17")
        self.assertEqual(res.data["max_teams"], 8)
        self.assertEqual(res.data["format_template"], "round_robin_single")
        self.assertEqual(res.data["status"], "active")
        self.assertTrue(res.data["is_active"])

        tournament = Tournament.objects.get(slug="copa-chever-futbol")
        self.assertTrue(tournament.is_active)
        self.assertEqual(tournament.status, "active")
        self.assertEqual(tournament.structure_mode, "structured")
        self.assertTrue(tournament.phases.filter(phase_type="round_robin").exists())

    def test_knockout_direct_template_creates_elimination_phases(self):
        self.assertIsNotNone(get_template("knockout_direct_8"))
        res = self.client.post(
            "/api/v1/sports/tournaments/",
            self._payload(
                slug="copa-eliminacion",
                name="Copa Eliminación",
                format_template="knockout_direct_8",
            ),
            format="json",
            HTTP_X_TENANT="chever-org",
        )
        self.assertEqual(res.status_code, 201, res.data)
        tournament = Tournament.objects.get(slug="copa-eliminacion")
        self.assertEqual(tournament.format_template, "knockout_direct_8")
        self.assertEqual(tournament.max_teams, 8)
        self.assertEqual(
            list(tournament.phases.order_by("order").values_list("slug", "phase_type")),
            [
                ("cuartos", "knockout"),
                ("semifinales", "knockout"),
                ("final", "knockout"),
            ],
        )


class FootballTeamAndRbacTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name="Chever Org", slug="chever-org")
        expires = timezone.now() + timedelta(days=30)
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner",
            password="secret123",
            organization=self.org,
            role="manager",
            sports_module_active=True,
            sports_module_expires_at=expires,
        )
        self.superuser = User.objects.create_user(
            email="root@example.com",
            username="root",
            password="secret123",
            organization=None,
            role="admin",
            is_superuser=True,
            is_staff=True,
            admin_level=1,
        )
        self.level1 = User.objects.create_user(
            email="l1@example.com",
            username="l1",
            password="secret123",
            organization=None,
            role="SUPER_ADMIN",
            admin_level=1,
        )
        self.tournament = Tournament.objects.create(
            name="Liga Municipal",
            slug="liga-municipal",
            sport_type="football",
            category="libre",
            posted_by=self.owner,
            organization=self.org,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            max_teams=8,
            is_active=True,
            status="active",
        )
        self.team = Team.objects.create(
            name="Atlético Chever",
            slug="atletico-chever",
            abbreviation="ACH",
            posted_by=self.owner,
            tournament=self.tournament,
            organization=self.org,
            coach_email="coach@example.com",
            logo="https://i.ibb.co/example/logo.png",
        )
        self.player = Player.objects.create(
            first_name="Carlos",
            last_name="Díaz",
            jersey_number=10,
            position="forward",
            id_number="1098765432",
            posted_by=self.owner,
            team=self.team,
            tournament=self.tournament,
        )
        self.client = APIClient()

    def test_team_logo_accepts_direct_url(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            "/api/v1/sports/teams/",
            {
                "name": "Deportivo Norte",
                "slug": "deportivo-norte",
                "abbreviation": "DN",
                "tournament": str(self.tournament.id),
                "logo": "https://i.ibb.co/abc123/escudo.png",
                "primary_color": "#112233",
                "secondary_color": "#FFFFFF",
            },
            format="json",
            HTTP_X_TENANT="chever-org",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(str(res.data["tournament"]), str(self.tournament.id))
        self.assertEqual(res.data["logo"], "https://i.ibb.co/abc123/escudo.png")
        created = Team.objects.get(slug="deportivo-norte")
        self.assertEqual(created.organization_id, self.org.id)

    def test_superuser_without_org_creates_team_on_tournament_org(self):
        self.client.force_authenticate(user=self.superuser)
        res = self.client.post(
            "/api/v1/sports/teams/",
            {
                "name": "Equipo Root",
                "slug": "equipo-root",
                "abbreviation": "ER",
                "tournament": str(self.tournament.id),
                "logo": "https://example.com/logo.png",
            },
            format="json",
            HTTP_X_TENANT="chever-org",
        )
        self.assertEqual(res.status_code, 201, res.data)
        created = Team.objects.get(slug="equipo-root")
        self.assertEqual(created.organization_id, self.org.id)
        self.assertEqual(created.posted_by_id, self.superuser.id)

    def test_super_admin_can_edit_tournament_created_by_another_user(self):
        self.client.force_authenticate(user=self.superuser)
        res = self.client.patch(
            f"/api/v1/sports/tournaments/{self.tournament.slug}/",
            {"name": "Liga Municipal Editada", "max_teams": 12},
            format="json",
            HTTP_X_TENANT="chever-org",
        )
        self.assertNotEqual(res.status_code, 403, res.data)
        self.assertEqual(res.status_code, 200, res.data)
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.name, "Liga Municipal Editada")
        self.assertEqual(self.tournament.max_teams, 12)

    def test_admin_level_1_can_update_player_of_other_team(self):
        self.client.force_authenticate(user=self.level1)
        res = self.client.patch(
            f"/api/v1/sports/players/{self.player.id}/",
            {"jersey_number": 9, "nickname": "El 9"},
            format="json",
            HTTP_X_TENANT="chever-org",
        )
        self.assertNotEqual(res.status_code, 403, res.data)
        self.assertEqual(res.status_code, 200, res.data)
        self.player.refresh_from_db()
        self.assertEqual(self.player.jersey_number, 9)

    def test_player_list_includes_card_fields(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(
            f"/api/v1/sports/players/?team={self.team.id}",
            HTTP_X_TENANT="chever-org",
        )
        self.assertEqual(res.status_code, 200)
        results = res.data["results"] if isinstance(res.data, dict) else res.data
        row = next(item for item in results if str(item["id"]) == str(self.player.id))
        self.assertEqual(row["team_logo"], self.team.logo)
        self.assertEqual(row["tournament_name"], self.tournament.name)
        self.assertEqual(row["tournament_category"], "Libre")

    def test_seed_source_resolves_teams_in_creation_order(self):
        second = Team.objects.create(
            name="Segundo",
            slug="segundo",
            abbreviation="SEG",
            posted_by=self.owner,
            tournament=self.tournament,
            organization=self.org,
        )
        first = resolve_team_source({"type": "seed", "rank": 1}, self.tournament)
        second_resolved = resolve_team_source({"type": "seed", "rank": 2}, self.tournament)
        self.assertEqual(first.id, self.team.id)
        self.assertEqual(second_resolved.id, second.id)
