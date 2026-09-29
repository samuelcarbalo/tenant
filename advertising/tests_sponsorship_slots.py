"""Cupo de hasta 3 patrocinadores simultáneos por torneo."""

from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from organizations.models import Organization
from sports.models import Tournament


class SponsorshipSlotTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org Ads", slug="org-ads")
        self.owner = User.objects.create_user(
            email="owner-ads@test.com",
            username="owner_ads",
            password="SecurePass123!",
            organization=self.org,
            role="manager",
        )
        self.tournament = Tournament.objects.create(
            name="Copa Ads",
            slug="copa-ads",
            sport_type="football",
            organization=self.org,
            posted_by=self.owner,
            start_date="2026-09-01",
            end_date="2026-12-01",
        )
        self.buyers = []
        for index in range(4):
            buyer = User.objects.create_user(
                email=f"buyer{index}@test.com",
                username=f"buyer_{index}",
                password="SecurePass123!",
                organization=self.org,
                role="manager",
                credits=1000,
            )
            self.buyers.append(buyer)

    def _purchase(self, buyer, title):
        client = APIClient()
        client.force_authenticate(user=buyer)
        return client.post(
            "/api/v1/advertising/sponsorships/purchase/",
            {
                "tournament": str(self.tournament.id),
                "plan": "month",
                "title": title,
                "image": "https://example.com/banner.png",
            },
            format="json",
        )

    def _availability(self):
        return APIClient().get(
            "/api/v1/advertising/sponsorships/availability/",
            {"slug": self.tournament.slug},
        ).json()

    def test_three_sponsors_then_sold_out(self):
        empty = self._availability()
        self.assertTrue(empty["available"])
        self.assertEqual(empty["slots_available"], 3)

        for index in range(3):
            res = self._purchase(self.buyers[index], f"Marca {index}")
            self.assertEqual(res.status_code, 201, res.content)

        full = self._availability()
        self.assertFalse(full["available"])
        self.assertEqual(full["slots_used"], 3)
        self.assertEqual(full["slots_available"], 0)
        self.assertEqual(
            [item["title"] for item in full["active_sponsorships"]],
            ["Marca 0", "Marca 1", "Marca 2"],
        )

        credits_before = self.buyers[3].credits
        blocked = self._purchase(self.buyers[3], "Marca 3")
        self.assertEqual(blocked.status_code, 400, blocked.content)
        self.assertIn("Cupo publicitario agotado para este mes", blocked.content.decode())
        self.buyers[3].refresh_from_db()
        self.assertEqual(self.buyers[3].credits, credits_before)

    def test_banners_by_position_rotate_up_to_three_in_purchase_order(self):
        for index in range(3):
            self._purchase(self.buyers[index], f"Marca {index}")
        res = APIClient().get(
            "/api/v1/sports/banners/by_position/",
            {"position": "tournament_detail", "tournament": str(self.tournament.id)},
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            [item["title"] for item in res.json()],
            ["Marca 0", "Marca 1", "Marca 2"],
        )
