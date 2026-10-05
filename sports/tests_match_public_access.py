"""Detalle público de partidos (finalizados y programados) para visitantes sin sesión."""

from datetime import timedelta

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

    def test_missing_match_returns_404(self):
        res = self.client.get("/api/v1/sports/matches/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(res.status_code, 404)

    def test_anonymous_cannot_mutate_match(self):
        res = self.client.post(
            f"/api/v1/sports/matches/{self.scheduled.id}/start_match/", {}, format="json"
        )
        self.assertEqual(res.status_code, 401)
