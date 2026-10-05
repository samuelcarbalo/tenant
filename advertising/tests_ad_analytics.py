"""Rastreo de impresiones de banners y reporte de métricas (Super Admin L1/L2)."""

from datetime import datetime, timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from advertising.analytics import DEDUP_WINDOW
from advertising.models import AdImpression
from authentication.models import User
from organizations.models import Organization
from sports.models import AdvertisementBanner


def _bogota(year, month, day, hour):
    return timezone.make_aware(datetime(year, month, day, hour), timezone.get_current_timezone())


class AdImpressionTrackingTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org Métricas", slug="org-metricas")
        self.owner = User.objects.create_user(
            email="anunciante@test.com",
            username="anunciante",
            password="SecurePass123!",
            organization=self.org,
            role="manager",
        )
        self.banner = AdvertisementBanner.objects.create(
            title="Banner Uno",
            image="https://cdn.test/b1.png",
            position="home_hero",
            posted_by=self.owner,
            start_date=timezone.localdate(),
        )
        self.url = f"/api/v1/ads/{self.banner.id}/track-impression/"

    def test_anonymous_impression_is_recorded_and_deduplicated(self):
        client = APIClient(HTTP_USER_AGENT="Mozilla/5.0 test", REMOTE_ADDR="10.0.0.1")
        first = client.post(self.url)
        second = client.post(self.url)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertTrue(first.json()["counted"])
        self.assertFalse(second.json()["counted"])
        self.assertEqual(AdImpression.objects.filter(ad=self.banner).count(), 1)
        self.banner.refresh_from_db()
        self.assertEqual(self.banner.impressions, 1)

        other_viewer = APIClient(HTTP_USER_AGENT="Mozilla/5.0 test", REMOTE_ADDR="10.0.0.2")
        self.assertTrue(other_viewer.post(self.url).json()["counted"])

    def test_same_viewer_counts_again_after_window(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        client.post(self.url)
        later = timezone.now() + DEDUP_WINDOW + timedelta(seconds=1)
        with mock.patch("advertising.analytics.timezone.now", return_value=later):
            res = client.post(self.url)
        self.assertTrue(res.json()["counted"])
        impression = AdImpression.objects.filter(ad=self.banner).first()
        self.assertEqual(impression.user, self.owner)

    def test_unknown_ad_returns_404(self):
        res = APIClient().post("/api/v1/ads/00000000-0000-0000-0000-000000000000/track-impression/")
        self.assertEqual(res.status_code, 404)

    def test_by_position_no_longer_counts_server_side(self):
        APIClient().get("/api/v1/sports/banners/by_position/", {"position": "home_hero"})
        self.banner.refresh_from_db()
        self.assertEqual(self.banner.impressions, 0)


class AdAnalyticsReportTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org Reporte", slug="org-reporte")
        self.manager = User.objects.create_user(
            email="manager-rep@test.com",
            username="manager_rep",
            password="SecurePass123!",
            organization=self.org,
            role="manager",
        )
        self.level2 = User.objects.create_user(
            email="l2-rep@test.com",
            username="l2_rep",
            password="SecurePass123!",
            organization=self.org,
            admin_level=2,
        )
        self.banner_a = AdvertisementBanner.objects.create(
            title="Marca A", image="https://cdn.test/a.png", posted_by=self.manager
        )
        self.banner_b = AdvertisementBanner.objects.create(
            title="Marca B", image="https://cdn.test/b.png", posted_by=self.manager, is_active=False
        )
        # 23:30 del 1 de octubre en Bogotá (04:30 UTC del 2) debe contar el día 1.
        self._impressions(self.banner_a, _bogota(2026, 10, 1, 23), 3)
        self._impressions(self.banner_a, _bogota(2026, 10, 3, 10), 1)
        self._impressions(self.banner_b, _bogota(2026, 10, 3, 12), 2)
        self._impressions(self.banner_a, _bogota(2026, 9, 1, 12), 5)
        self.url = "/api/v1/admin/ads/analytics/"

    def _impressions(self, banner, when, count):
        for _ in range(count):
            impression = AdImpression.objects.create(ad=banner)
            AdImpression.objects.filter(pk=impression.pk).update(viewed_at=when)

    def _get(self, user, params):
        client = APIClient()
        client.force_authenticate(user)
        return client.get(self.url, params)

    def test_only_super_admins_can_read(self):
        self.assertEqual(self._get(self.manager, {}).status_code, 403)
        self.assertEqual(APIClient().get(self.url).status_code, 401)

    def test_daily_breakdown_and_totals(self):
        res = self._get(self.level2, {"start": "2026-10-01", "end": "2026-10-04"})
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(
            [(d["date"], d["views"]) for d in body["daily"]],
            [("2026-10-01", 3), ("2026-10-02", 0), ("2026-10-03", 3), ("2026-10-04", 0)],
        )
        self.assertEqual(body["total_views"], 6)
        self.assertEqual(body["peak_day"]["date"], "2026-10-01")

        ads = {ad["title"]: ad for ad in body["ads"]}
        self.assertEqual(ads["Marca A"]["views_in_range"], 4)
        self.assertEqual(ads["Marca A"]["total_views"], 9)
        self.assertEqual(ads["Marca B"]["views_in_range"], 2)
        self.assertFalse(ads["Marca B"]["is_active"])
        self.assertEqual(ads["Marca A"]["sponsor"], self.manager.full_name)

    def test_filter_by_single_ad(self):
        res = self._get(
            self.level2, {"start": "2026-10-01", "end": "2026-10-04", "ad": str(self.banner_b.id)}
        )
        body = res.json()
        self.assertEqual(body["ad"]["title"], "Marca B")
        self.assertEqual(body["total_views"], 2)
        self.assertEqual(body["daily"][2]["views"], 2)

    def test_invalid_range_returns_400(self):
        res = self._get(self.level2, {"start": "2026-10-05", "end": "2026-10-01"})
        self.assertEqual(res.status_code, 400)
