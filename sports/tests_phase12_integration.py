"""Pruebas de integración Fase 1 y 2: cuadrangular softbol completo."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import Tournament, Team, Match, TournamentPhase, CompetitionGroup
from sports.services.structure import (
    apply_format_template,
    assign_teams_to_group,
    generate_round_robin_fixtures,
)
from sports.scoring import MatchResultService, StandingsService
from sports.formats.templates import list_templates


class Phase12IntegrationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Municipio Test", slug="mun-test")
        self.user = User.objects.create_user(
            email="org@test.com",
            username="orgmanager",
            password="SecurePass123!",
            organization=self.org,
            role="manager",
            credits=100,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.tournament = Tournament.objects.create(
            name="Copa Softbol Municipal",
            slug="copa-softbol-municipal",
            sport_type="softball",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-06-15",
            end_date="2026-06-15",
            registration_deadline="2026-06-10",
        )
        apply_format_template(self.tournament, "single_day_quadrangular")

        self.teams = []
        for i, name in enumerate(["Tigres", "Leones", "Águilas", "Toros"], start=1):
            self.teams.append(
                Team.objects.create(
                    name=name,
                    slug=f"equipo-{i}",
                    abbreviation=f"E{i}",
                    tournament=self.tournament,
                    organization=self.org,
                    posted_by=self.user,
                )
            )

        self.phase = self.tournament.phases.get(slug="cuadrangular")
        self.group = self.phase.groups.get(slug="cuadrangular")
        assign_teams_to_group(self.group, [t.id for t in self.teams])

    def test_format_templates_include_softball_quadrangular(self):
        templates = list_templates("softball")
        ids = [t["id"] for t in templates]
        self.assertIn("single_day_quadrangular", ids)

    def test_structure_api_returns_phases_and_groups(self):
        res = self.client.get(
            f"/api/v1/sports/tournaments/{self.tournament.slug}/structure/"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["structure_mode"], "structured")
        self.assertEqual(len(data["phases"]), 1)
        self.assertEqual(len(data["phases"][0]["groups"]), 1)
        self.assertEqual(data["phases"][0]["groups"][0]["teams_count"], 4)

    def test_full_quadrangular_flow_softball_scoring(self):
        generate_round_robin_fixtures(
            tournament=self.tournament,
            phase=self.phase,
            group=self.group,
            posted_by=self.user,
            match_date=timezone.now(),
            venue="Campo Municipal",
        )
        matches = Match.objects.filter(tournament=self.tournament, phase=self.phase)
        self.assertEqual(matches.count(), 6)

        results = [(5, 2), (3, 4), (6, 1), (2, 5), (4, 3), (1, 6)]
        for match, (hr, ar) in zip(matches.order_by("id"), results):
            MatchResultService.finalize_match(
                match, {"home_runs": hr, "away_runs": ar}
            )

        standings = StandingsService.compute(
            self.tournament, phase=self.phase, group=self.group
        )
        self.assertEqual(len(standings), 4)
        self.assertEqual(standings[0]["played"], 3)
        self.assertGreater(standings[0]["runs"], 0)

        res = self.client.get(
            f"/api/v1/sports/tournaments/{self.tournament.slug}/standings/",
            {"phase": "cuadrangular", "group": "cuadrangular"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 4)
        self.assertIn("runs", res.json()[0])
        self.assertIn("average", res.json()[0])

        for team in self.teams:
            team.refresh_from_db()
            self.assertEqual(team.played, 3)
        self.assertEqual(
            Match.objects.filter(tournament=self.tournament, status="finished").count(), 6
        )

    def test_standings_scoped_excludes_other_groups(self):
        apply_format_template(
            Tournament.objects.create(
                name="Multi",
                slug="multi-cua",
                sport_type="softball",
                organization=self.org,
                posted_by=self.user,
                start_date="2026-06-15",
                end_date="2026-06-16",
            ),
            "multi_quadrangular",
            group_count=2,
        )
        t2 = Tournament.objects.get(slug="multi-cua")
        phase = t2.phases.first()
        g_a, g_b = list(phase.groups.order_by("order"))
        teams_a = self.teams[:2]
        teams_b = [
            Team.objects.create(
                name=f"B{i}",
                slug=f"b-{i}",
                abbreviation=f"B{i}",
                tournament=t2,
                organization=self.org,
                posted_by=self.user,
            )
            for i in range(1, 3)
        ]
        assign_teams_to_group(g_a, [t.id for t in teams_a])
        assign_teams_to_group(g_b, [t.id for t in teams_b])

        m = Match.objects.create(
            tournament=t2,
            posted_by=self.user,
            home_team=teams_a[0],
            away_team=teams_a[1],
            match_date=timezone.now(),
            phase=phase,
            group=g_a,
            match_type="group",
            status="finished",
        )
        MatchResultService.finalize_match(m, {"home_runs": 3, "away_runs": 1})

        st_a = StandingsService.compute(t2, phase=phase, group=g_a)
        st_b = StandingsService.compute(t2, phase=phase, group=g_b)
        self.assertEqual(len(st_a), 2)
        self.assertEqual(st_a[0]["played"], 1)
        self.assertEqual(len(st_b), 2)
        self.assertEqual(st_b[0]["played"], 0)
