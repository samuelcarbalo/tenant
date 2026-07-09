from django.test import TestCase
from django.utils import timezone
from authentication.models import User
from organizations.models import Organization
from sports.models import Tournament, Team, Match, TournamentPhase, CompetitionGroup, GroupMembership
from sports.scoring import MatchResultService, StandingsService


class SoftballScoringTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        self.user = User.objects.create_user(
            email="coach@test.com",
            username="coachsoftbol",
            password="pass12345",
            organization=self.org,
            role="manager",
        )
        self.tournament = Tournament.objects.create(
            name="Copa Softbol",
            slug="copa-softbol",
            sport_type="softball",
            organization=self.org,
            posted_by=self.user,
            start_date="2026-06-01",
            end_date="2026-06-01",
            structure_mode="structured",
            format_template="single_day_quadrangular",
        )
        self.phase = TournamentPhase.objects.create(
            tournament=self.tournament,
            name="Cuadrangular",
            slug="cuadrangular",
            phase_type="round_robin",
            order=1,
            status="active",
        )
        self.group = CompetitionGroup.objects.create(
            phase=self.phase,
            name="Cuadrangular",
            slug="cuadrangular",
            order=1,
            max_teams=4,
        )
        self.team_a = Team.objects.create(
            name="Equipo A",
            slug="equipo-a",
            abbreviation="EA",
            tournament=self.tournament,
            organization=self.org,
            posted_by=self.user,
        )
        self.team_b = Team.objects.create(
            name="Equipo B",
            slug="equipo-b",
            abbreviation="EB",
            tournament=self.tournament,
            organization=self.org,
            posted_by=self.user,
        )
        GroupMembership.objects.create(group=self.group, team=self.team_a, seed=1)
        GroupMembership.objects.create(group=self.group, team=self.team_b, seed=2)

    def _create_match(self, home_runs, away_runs):
        match = Match.objects.create(
            tournament=self.tournament,
            posted_by=self.user,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=timezone.now(),
            phase=self.phase,
            group=self.group,
            match_type="group",
            status="scheduled",
        )
        MatchResultService.finalize_match(
            match,
            {"home_runs": home_runs, "away_runs": away_runs},
        )
        return match

    def test_softball_winner_by_runs(self):
        self._create_match(5, 3)
        self.team_a.refresh_from_db()
        self.team_b.refresh_from_db()
        self.assertEqual(self.team_a.won, 1)
        self.assertEqual(self.team_b.lost, 1)
        self.assertEqual(self.team_a.runs, 5)
        self.assertEqual(self.team_b.runs_against, 5)

    def test_standings_by_group(self):
        self._create_match(4, 2)
        standings = StandingsService.compute(
            self.tournament, phase=self.phase, group=self.group
        )
        self.assertEqual(len(standings), 2)
        self.assertEqual(standings[0]["team"].id, self.team_a.id)
        self.assertEqual(standings[0]["runs"], 4)
