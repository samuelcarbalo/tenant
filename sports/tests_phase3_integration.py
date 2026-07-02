"""Pruebas Fase 3: avance a eliminatoria y bracket."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import Match, Tournament, Team
from sports.services.structure import (
    apply_format_template,
    assign_teams_to_group,
    generate_round_robin_fixtures,
)
from sports.services.advancement import advance_phase, propagate_bracket_after_match
from sports.scoring import MatchResultService


class Phase3IntegrationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Municipio", slug="mun")
        self.user = User.objects.create_user(
            email="m@test.com",
            username="manager1",
            password="SecurePass123!",
            organization=self.org,
            role="manager",
            credits=100,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.tournament = Tournament.objects.create(
            name="Copa Cuad Final",
            slug="copa-cuad-final",
            sport_type="softball",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-07-01",
            end_date="2026-07-01",
        )
        apply_format_template(self.tournament, "single_quadrangular_final")

        self.teams = []
        for i, name in enumerate(["Alpha", "Beta", "Gamma", "Delta"], start=1):
            self.teams.append(
                Team.objects.create(
                    name=name,
                    slug=f"t-{i}",
                    abbreviation=f"T{i}",
                    tournament=self.tournament,
                    organization=self.org,
                    posted_by=self.user,
                )
            )

        phase = self.tournament.phases.get(slug="cuadrangular")
        group = phase.groups.get(slug="cuadrangular")
        assign_teams_to_group(group, [t.id for t in self.teams])
        generate_round_robin_fixtures(
            tournament=self.tournament,
            phase=phase,
            group=group,
            posted_by=self.user,
            match_date=timezone.now(),
        )
        self.phase = phase
        self.group = group

    def _finish_quadrangular_with_clear_ranking(self):
        """Alpha gana todos; Beta segundo; resto pierde."""
        alpha, beta, gamma, delta = self.teams
        pairs = [
            (alpha, beta, 5, 2),
            (alpha, gamma, 4, 1),
            (alpha, delta, 6, 0),
            (beta, gamma, 3, 2),
            (beta, delta, 4, 3),
            (gamma, delta, 2, 1),
        ]
        for home, away, hr, ar in pairs:
            match = Match.objects.get(
                tournament=self.tournament,
                home_team=home,
                away_team=away,
                phase=self.phase,
            )
            MatchResultService.finalize_match(match, {"home_runs": hr, "away_runs": ar})

    def test_advance_phase_creates_final(self):
        self._finish_quadrangular_with_clear_ranking()

        result = advance_phase(
            self.tournament,
            "cuadrangular",
            self.user,
            match_date=timezone.now(),
        )
        self.assertEqual(result["from_phase"].status, "finished")
        self.assertEqual(result["next_phase"].slug, "final")
        self.assertEqual(len(result["matches_created"]), 1)

        final = result["matches_created"][0]
        self.assertEqual(final.match_type, "knockout")
        names = {final.home_team.name, final.away_team.name}
        self.assertEqual(names, {"Alpha", "Beta"})

    def test_advance_phase_api(self):
        self._finish_quadrangular_with_clear_ranking()
        res = self.client.post(
            f"/api/v1/sports/tournaments/{self.tournament.slug}/advance_phase/",
            {"from_phase": "cuadrangular", "match_date": timezone.now().isoformat()},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["matches_created"]), 1)

    def test_bracket_api_after_advance(self):
        self._finish_quadrangular_with_clear_ranking()
        advance_phase(self.tournament, "cuadrangular", self.user)

        res = self.client.get(
            f"/api/v1/sports/tournaments/{self.tournament.slug}/bracket/",
            {"phase": "final"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["nodes"]), 1)
        node = res.json()["nodes"][0]
        self.assertIsNotNone(node["home_team"])
        self.assertIsNotNone(node["away_team"])

    def test_propagate_bracket_after_semifinal(self):
        apply_format_template(
            Tournament.objects.create(
                name="Semis",
                slug="semis-test",
                sport_type="softball",
                organization=self.org,
                posted_by=self.user,
                start_date="2026-07-01",
                end_date="2026-07-02",
            ),
            "round_robin_knockout_8",
        )
        t = Tournament.objects.get(slug="semis-test")
        reg = t.phases.get(slug="regular")
        teams = [
            Team.objects.create(
                name=f"E{i}",
                slug=f"e-{i}",
                abbreviation=f"E{i}",
                tournament=t,
                organization=self.org,
                posted_by=self.user,
            )
            for i in range(1, 5)
        ]
        generate_round_robin_fixtures(
            t, reg, None, self.user, timezone.now()
        )
        for m in Match.objects.filter(tournament=t, phase=reg):
            MatchResultService.finalize_match(m, {"home_runs": 3, "away_runs": 1})

        advance_phase(t, "regular", self.user)
        semis = Match.objects.filter(tournament=t, phase__slug="semifinales")
        self.assertEqual(semis.count(), 2)

        for m in semis:
            MatchResultService.finalize_match(m, {"home_runs": 2, "away_runs": 0})

        final_matches = Match.objects.filter(tournament=t, phase__slug="final")
        self.assertEqual(final_matches.count(), 1)
