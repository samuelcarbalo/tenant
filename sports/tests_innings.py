from django.test import TestCase
from django.utils import timezone

from authentication.models import User
from organizations.models import Organization
from sports.models import Tournament, Team, Match, MatchInning
from sports.services.innings import (
    upsert_inning,
    recompute_match_from_innings,
    check_game_over,
    build_line_score,
)


class SoftballInningsTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org", slug="org")
        self.user = User.objects.create_user(
            email="c@t.com", username="c", password="pass12345",
            organization=self.org, role="manager",
        )
        self.tournament = Tournament.objects.create(
            name="Copa", slug="copa", sport_type="softball",
            organization=self.org, posted_by=self.user,
            start_date="2026-06-01", end_date="2026-06-01",
            regulation_innings=7, mercy_rule_enabled=True,
        )
        self.home = Team.objects.create(
            name="Local", slug="local", abbreviation="LOC",
            tournament=self.tournament, organization=self.org, posted_by=self.user,
        )
        self.away = Team.objects.create(
            name="Visita", slug="visita", abbreviation="VIS",
            tournament=self.tournament, organization=self.org, posted_by=self.user,
        )

    def _match(self):
        return Match.objects.create(
            tournament=self.tournament, posted_by=self.user,
            home_team=self.home, away_team=self.away,
            match_date=timezone.now(), status="live",
        )

    def _play(self, match, top_runs, bottom_runs, complete_bottom=True):
        """Juega entradas completas. top_runs/bottom_runs son listas por entrada."""
        for i, (t, b) in enumerate(zip(top_runs, bottom_runs), start=1):
            upsert_inning(match, i, "top", runs=t, is_complete=True)
            last = i == len(top_runs)
            upsert_inning(
                match, i, "bottom", runs=b,
                is_complete=(complete_bottom or not last),
            )

    def test_totals_from_innings(self):
        m = self._match()
        self._play(m, [0, 1, 2], [1, 0, 0])
        home, away = recompute_match_from_innings(m, save=False)
        self.assertEqual(away, 3)  # visitante batea en la alta
        self.assertEqual(home, 1)  # local batea en la baja
        m.refresh_from_db()
        self.assertEqual(m.home_score, m.home_runs)

    def test_regulation_end_no_tie(self):
        m = self._match()
        self._play(m, [1, 1, 1, 1, 1, 1, 1], [0, 0, 1, 0, 0, 1, 0])
        game = check_game_over(m)
        self.assertTrue(game["over"])
        self.assertEqual(game["winner"], "away")
        self.assertEqual(game["reason"], "Fin de regulación")

    def test_tie_after_regulation_continues(self):
        m = self._match()
        self._play(m, [1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1])
        game = check_game_over(m)
        self.assertFalse(game["over"])

    def test_walk_off(self):
        m = self._match()
        # 6 entradas empatadas, en la baja de la 7ma el local anota
        self._play(m, [1, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0])
        upsert_inning(m, 7, "top", runs=0, is_complete=True)
        upsert_inning(m, 7, "bottom", runs=1, is_complete=False)
        game = check_game_over(m)
        self.assertTrue(game["over"])
        self.assertEqual(game["reason"], "Walk-off")
        self.assertEqual(game["winner"], "home")

    def test_mercy_rule(self):
        m = self._match()
        # Visitante saca 15 tras 4 entradas completas
        self._play(m, [4, 4, 4, 3], [0, 0, 0, 0])
        game = check_game_over(m)
        self.assertTrue(game["over"])
        self.assertIn("Nocaut", game["reason"])
        self.assertEqual(game["winner"], "away")

    def test_line_score_shape(self):
        m = self._match()
        self._play(m, [0, 2], [1, 0])
        ls = build_line_score(m)
        self.assertEqual(ls["innings_count"], 2)
        self.assertEqual(ls["away"]["runs"], 2)
        self.assertEqual(ls["home"]["runs"], 1)
        self.assertEqual(len(ls["home"]["line"]), 2)
