"""
Prueba integral Fase 1 + 2: scoring softbol, estructura, fixture, standings.
Ejecutar:
  python manage.py test sports.tests_integration_phases --settings=config.settings.development
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import (
    Tournament,
    Team,
    Match,
    TournamentPhase,
    CompetitionGroup,
)
from sports.scoring import MatchResultService, StandingsService
from sports.services.structure import apply_format_template, assign_teams_to_group, generate_round_robin_fixtures


class Phase1And2IntegrationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Municipio Test", slug="municipio-test")
        self.user = User.objects.create_user(
            email="organizer@test.com",
            username="organizer",
            password="TestPass123!",
            organization=self.org,
            role="manager",
            credits=500,
            sports_module_active=True,
            sports_module_expires_at=timezone.now() + timedelta(days=30),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _create_softball_quadrangular(self):
        t = Tournament.objects.create(
            name="Copa Softbol Verano",
            slug="copa-softbol-verano",
            sport_type="softball",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-06-15",
            end_date="2026-06-15",
            registration_deadline="2026-06-10",
            max_teams=4,
            min_players_per_team=9,
            max_players_per_team=20,
        )
        apply_format_template(t, "single_day_quadrangular")
        t.refresh_from_db()
        teams = []
        for i, name in enumerate(["Tigres", "Leones", "Aguilas", "Toros"], start=1):
            teams.append(
                Team.objects.create(
                    name=name,
                    slug=f"equipo-{i}",
                    abbreviation=f"E{i}",
                    tournament=t,
                    organization=self.org,
                    posted_by=self.user,
                )
            )
        group = t.phases.first().groups.first()
        assign_teams_to_group(group, [str(tm.id) for tm in teams])
        phase = t.phases.first()
        generate_round_robin_fixtures(
            tournament=t,
            phase=phase,
            group=group,
            posted_by=self.user,
            match_date=timezone.now(),
            venue="Campo Municipal",
        )
        return t, group, teams

    def test_phase1_softball_scoring_no_draws(self):
        """Softbol: ganador por carreras, sin empates."""
        t, group, teams = self._create_softball_quadrangular()
        match = Match.objects.filter(tournament=t).first()
        with self.assertRaises(ValueError):
            MatchResultService.determine_outcome(3, 3, __import__("sports.scoring.config", fromlist=["get_scoring_config"]).get_scoring_config(t))

        MatchResultService.finalize_match(match, {"home_runs": 7, "away_runs": 4})
        match.refresh_from_db()
        self.assertEqual(match.status, "finished")
        self.assertEqual(match.home_runs, 7)
        self.assertEqual(match.home_score, 7)

        home = match.home_team
        home.refresh_from_db()
        self.assertEqual(home.won, 1)
        self.assertEqual(home.runs, 7)

    def test_phase1_football_scoring_allows_draw(self):
        t = Tournament.objects.create(
            name="Liga Futbol",
            slug="liga-futbol",
            sport_type="football",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-06-01",
            end_date="2026-07-01",
        )
        a = Team.objects.create(
            name="A", slug="a", abbreviation="A", tournament=t, organization=self.org, posted_by=self.user
        )
        b = Team.objects.create(
            name="B", slug="b", abbreviation="B", tournament=t, organization=self.org, posted_by=self.user
        )
        m = Match.objects.create(
            tournament=t,
            posted_by=self.user,
            home_team=a,
            away_team=b,
            match_date=timezone.now(),
        )
        MatchResultService.finalize_match(m, {"home_score": 1, "away_score": 1})
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.drawn, 1)
        self.assertEqual(b.drawn, 1)
        self.assertEqual(a.points, 1)

    def test_phase2_quadrangular_fixture_and_standings(self):
        t, group, teams = self._create_softball_quadrangular()
        self.assertEqual(Match.objects.filter(tournament=t).count(), 6)
        self.assertEqual(t.structure_mode, "structured")
        self.assertEqual(group.memberships.count(), 4)

        matches = list(Match.objects.filter(tournament=t).order_by("id"))
        results = [(5, 2), (3, 4), (6, 1), (2, 5), (4, 3), (1, 6)]
        for match, (hr, ar) in zip(matches, results):
            MatchResultService.finalize_match(match, {"home_runs": hr, "away_runs": ar})

        standings = StandingsService.compute(t, phase=t.phases.first(), group=group)
        self.assertEqual(len(standings), 4)
        self.assertEqual(standings[0]["played"], 3)
        self.assertIn("runs", standings[0])
        self.assertGreater(standings[0]["points"], 0)

    def test_phase2_api_structure_and_standings(self):
        t, group, _ = self._create_softball_quadrangular()

        struct_resp = self.client.get(f"/api/v1/sports/tournaments/{t.slug}/structure/")
        self.assertEqual(struct_resp.status_code, 200)
        self.assertEqual(struct_resp.data["structure_mode"], "structured")
        self.assertEqual(len(struct_resp.data["phases"]), 1)
        self.assertEqual(len(struct_resp.data["phases"][0]["groups"]), 1)

        templates_resp = self.client.get("/api/v1/sports/tournaments/format_templates/?sport_type=softball")
        self.assertEqual(templates_resp.status_code, 200)
        ids = [x["id"] for x in templates_resp.data]
        self.assertIn("single_day_quadrangular", ids)

        standings_resp = self.client.get(
            f"/api/v1/sports/tournaments/{t.slug}/standings/",
            {"phase": "cuadrangular", "group": "cuadrangular"},
        )
        self.assertEqual(standings_resp.status_code, 200)
        self.assertEqual(len(standings_resp.data), 4)

    def test_phase2_create_tournament_with_template(self):
        resp = self.client.post(
            "/api/v1/sports/tournaments/",
            {
                "name": "Nuevo Cuadrangular",
                "slug": "nuevo-cuadrangular",
                "description": "",
                "sport_type": "softball",
                "start_date": "2026-06-20",
                "end_date": "2026-06-20",
                "registration_deadline": "2026-06-18",
                "max_teams": 4,
                "min_players_per_team": 9,
                "max_players_per_team": 20,
                "format_template": "single_day_quadrangular",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        t = Tournament.objects.get(slug="nuevo-cuadrangular")
        self.assertEqual(t.structure_mode, "structured")
        self.assertEqual(t.phases.count(), 1)
        self.assertEqual(t.phases.first().groups.count(), 1)
