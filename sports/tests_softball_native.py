"""Tests de la experiencia nativa de softbol: eventos/box score, marcador por
entradas vía API y desempate head-to-head."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import Tournament, Team, Player, Match
from sports.scoring import StandingsService
from sports.scoring.config import get_scoring_config


class SoftballNativeBase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org", slug="org")
        self.user = User.objects.create_user(
            email="c@t.com", username="c", password="pass12345",
            organization=self.org, role="manager",
            sports_module_active=True,
            sports_module_expires_at=timezone.now() + timedelta(days=30),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.t = Tournament.objects.create(
            name="Copa", slug="copa", sport_type="softball",
            organization=self.org, posted_by=self.user,
            start_date="2026-06-01", end_date="2026-06-01",
            regulation_innings=7,
        )
        self.home = Team.objects.create(
            name="Local", slug="local", abbreviation="LOC",
            tournament=self.t, organization=self.org, posted_by=self.user,
        )
        self.away = Team.objects.create(
            name="Visita", slug="visita", abbreviation="VIS",
            tournament=self.t, organization=self.org, posted_by=self.user,
        )

    def _match(self):
        return Match.objects.create(
            tournament=self.t, posted_by=self.user,
            home_team=self.home, away_team=self.away,
            match_date=timezone.now(), status="live",
        )

    def _player(self, team):
        return Player.objects.create(
            first_name="Juan", last_name="Perez", jersey_number=10,
            position="first_base", team=team, tournament=self.t,
            posted_by=self.user,
        )


class SoftballEventStatsTests(SoftballNativeBase):
    def _add_event(self, match, player, event_type, rbi=0):
        return self.client.post(
            f"/api/v1/sports/matches/{match.id}/add_event/",
            {
                "event_type": event_type,
                "player": str(player.id),
                "team": str(player.team.id),
                "rbi": rbi,
            },
            format="json",
        )

    def test_hit_updates_batting_stats(self):
        m = self._match()
        p = self._player(self.home)
        res = self._add_event(m, p, "single")
        self.assertEqual(res.status_code, 201)
        p.refresh_from_db()
        self.assertEqual(p.hits, 1)
        self.assertEqual(p.at_bats, 1)
        self.assertEqual(p.batting_average, 1.0)

    def test_home_run_and_avg(self):
        m = self._match()
        p = self._player(self.home)
        self._add_event(m, p, "home_run")
        self._add_event(m, p, "strikeout")
        p.refresh_from_db()
        self.assertEqual(p.home_runs, 1)
        self.assertEqual(p.hits, 1)
        self.assertEqual(p.at_bats, 2)
        self.assertAlmostEqual(p.batting_average, 0.5)

    def test_walk_no_at_bat(self):
        m = self._match()
        p = self._player(self.home)
        self._add_event(m, p, "walk")
        p.refresh_from_db()
        self.assertEqual(p.walks, 1)
        self.assertEqual(p.at_bats, 0)

    def test_rbi_and_runs(self):
        m = self._match()
        p = self._player(self.home)
        self._add_event(m, p, "rbi", rbi=2)
        self._add_event(m, p, "run")
        p.refresh_from_db()
        self.assertEqual(p.rbis, 2)
        self.assertEqual(p.runs_scored, 1)

    def test_events_do_not_change_score(self):
        m = self._match()
        p = self._player(self.home)
        self._add_event(m, p, "home_run")
        m.refresh_from_db()
        # El marcador solo se maneja por entradas, no por eventos
        self.assertIn(m.home_runs, (None, 0))


class SoftballRecordInningAPITests(SoftballNativeBase):
    def _record(self, match, number, half, **kwargs):
        payload = {"number": number, "half": half, **kwargs}
        return self.client.post(
            f"/api/v1/sports/matches/{match.id}/record_inning/",
            payload, format="json",
        )

    def test_record_inning_updates_line_score(self):
        m = self._match()
        res = self._record(m, 1, "top", runs=2, is_complete=True)
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(res.data.get("line_score"))
        self.assertEqual(res.data["line_score"]["away"]["runs"], 2)

    def test_auto_finish_by_mercy(self):
        m = self._match()
        # Visitante saca 15 tras 4 entradas -> nocaut
        for n, r in [(1, 4), (2, 4), (3, 4), (4, 3)]:
            self._record(m, n, "top", runs=r, is_complete=True)
            self._record(m, n, "bottom", runs=0, is_complete=True)
        m.refresh_from_db()
        self.assertEqual(m.status, "finished")
        self.assertEqual(m.away_runs, 15)


class SoftballHeadToHeadTests(SoftballNativeBase):
    def test_head_to_head_breaks_tie(self):
        """Con métricas previas empatadas, gana quien ganó el enfrentamiento directo."""
        config = get_scoring_config(self.t)
        # Local venció a Visita 5-3
        match = Match.objects.create(
            tournament=self.t, posted_by=self.user,
            home_team=self.home, away_team=self.away,
            match_date=timezone.now(), status="finished",
            home_runs=5, away_runs=3, home_score=5, away_score=3,
        )
        row_home = StandingsService._empty_row(self.home)
        row_away = StandingsService._empty_row(self.away)
        for row in (row_home, row_away):
            row["points"] = 2
            row["won"] = 1
            row["average"] = 1.0
            row["runs"] = 5

        self.assertLess(
            StandingsService._compare_rows(row_home, row_away, config, [match]), 0
        )
        self.assertGreater(
            StandingsService._compare_rows(row_away, row_home, config, [match]), 0
        )
