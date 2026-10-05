"""Detalle público de partidos (finalizados y programados) para visitantes sin sesión."""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.db import DatabaseError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import Match, Team, Tournament


class MatchPublicAccessTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org Partidos", slug="org-partidos")
        self.owner = User.objects.create_user(
            email="owner-partidos@test.com",
            username="owner_partidos",
            password="SecurePass123!",
            organization=self.org,
            role="manager",
        )
        self.tournament = Tournament.objects.create(
            name="Copa Partidos",
            slug="copa-partidos",
            sport_type="football",
            organization=self.org,
            posted_by=self.owner,
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        teams = [
            Team.objects.create(
                name=name,
                slug=name.lower(),
                abbreviation=name[:3].upper(),
                tournament=self.tournament,
                organization=self.org,
                posted_by=self.owner,
            )
            for name in ("Local", "Visita")
        ]
        now = timezone.now()
        self.finished = Match.objects.create(
            tournament=self.tournament,
            posted_by=self.owner,
            home_team=teams[0],
            away_team=teams[1],
            match_date=now - timedelta(days=90),
            status="finished",
            home_score=2,
            away_score=1,
        )
        self.scheduled = Match.objects.create(
            tournament=self.tournament,
            posted_by=self.owner,
            home_team=teams[1],
            away_team=teams[0],
            match_date=now + timedelta(days=10),
            status="scheduled",
        )
        self.client = APIClient()

    def test_anonymous_can_read_past_and_upcoming_match_detail(self):
        for match in (self.finished, self.scheduled):
            for suffix in ("", "periods/", "lineup/"):
                res = self.client.get(f"/api/v1/sports/matches/{match.id}/{suffix}")
                self.assertEqual(res.status_code, 200, f"{match.status} {suffix}: {res.content}")

    def test_lineup_database_error_returns_empty_lineup(self):
        with mock.patch(
            "sports.views.MatchLineup.objects.filter",
            side_effect=DatabaseError('column players.phone does not exist'),
        ):
            res = self.client.get(f"/api/v1/sports/matches/{self.finished.id}/lineup/")
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body["message"], "Alineación no disponible")
        self.assertEqual(body["lineup"], [])
        self.assertEqual(body["home_team"]["starters"], [])
        self.assertEqual(body["away_team"]["substitutes"], [])

    def test_missing_match_returns_404(self):
        res = self.client.get("/api/v1/sports/matches/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(res.status_code, 404)

    def test_anonymous_cannot_mutate_match(self):
        res = self.client.post(
            f"/api/v1/sports/matches/{self.scheduled.id}/start_match/", {}, format="json"
        )
        self.assertEqual(res.status_code, 401)

    def test_partial_patch_without_teams_updates_match(self):
        admin = User.objects.create_user(
            email="l2-partidos@test.com",
            username="l2_partidos",
            password="SecurePass123!",
            organization=self.org,
            admin_level=2,
        )
        self.client.force_authenticate(admin)
        new_date = (timezone.now() + timedelta(days=20)).replace(microsecond=0)
        res = self.client.patch(
            f"/api/v1/sports/matches/{self.scheduled.id}/",
            {"match_date": new_date.isoformat(), "venue": "Estadio Nuevo"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.scheduled.refresh_from_db()
        self.assertEqual(self.scheduled.venue, "Estadio Nuevo")
        self.assertEqual(self.scheduled.match_date, new_date)

    def test_match_date_is_interpreted_in_bogota_time(self):
        admin = User.objects.create_user(
            email="l2tz-partidos@test.com",
            username="l2tz_partidos",
            password="SecurePass123!",
            organization=self.org,
            admin_level=2,
        )
        self.client.force_authenticate(admin)
        expected_utc = datetime(2026, 10, 6, 4, 0, tzinfo=dt_timezone.utc)
        for value in ("2026-10-05T23:00:00-05:00", "2026-10-05T23:00"):
            res = self.client.patch(
                f"/api/v1/sports/matches/{self.scheduled.id}/",
                {"match_date": value},
                format="json",
            )
            self.assertEqual(res.status_code, 200, res.content)
            self.scheduled.refresh_from_db()
            self.assertEqual(self.scheduled.match_date, expected_utc, value)

        detail = self.client.get(f"/api/v1/sports/matches/{self.scheduled.id}/").json()
        self.assertEqual(detail["match_date"], "2026-10-05T23:00:00-05:00")

    def test_patch_same_teams_is_rejected(self):
        admin = User.objects.create_user(
            email="l2b-partidos@test.com",
            username="l2b_partidos",
            password="SecurePass123!",
            organization=self.org,
            admin_level=2,
        )
        self.client.force_authenticate(admin)
        res = self.client.patch(
            f"/api/v1/sports/matches/{self.scheduled.id}/",
            {"away_team": str(self.scheduled.home_team_id)},
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
