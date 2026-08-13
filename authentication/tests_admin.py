from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from organizations.models import Organization

User = get_user_model()


class SeedSuperuserTests(TestCase):
    def test_seed_creates_platform_superuser(self):
        call_command("seed_superuser")
        user = User.objects.get(email="carbalosamuel@hotmail.com")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_unlimited_credits)
        self.assertIsNone(user.organization_id)
        self.assertTrue(user.check_password("Vivayo123!"))

    def test_seed_is_idempotent(self):
        call_command("seed_superuser")
        call_command("seed_superuser")
        self.assertEqual(
            User.objects.filter(email="carbalosamuel@hotmail.com").count(), 1
        )


class AdminUsersApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="boss@platform.com",
            username="boss",
            password="SecurePass123!",
        )
        self.admin.is_unlimited_credits = True
        self.admin.save(update_fields=["is_unlimited_credits"])
        self.org = Organization.objects.create(name="Org", slug="org")
        self.regular = User.objects.create_user(
            email="member@org.com",
            username="member",
            password="SecurePass123!",
            organization=self.org,
            credits=10,
        )

    def test_regular_user_cannot_list(self):
        self.client.force_authenticate(self.regular)
        res = self.client.get("/api/v1/admin/users/")
        self.assertEqual(res.status_code, 403)

    def test_admin_lists_and_adjusts_credits(self):
        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/v1/admin/users/?search=member")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.data["count"], 1)

        res = self.client.post(
            f"/api/v1/admin/users/{self.regular.id}/credits/",
            {"credits": 80, "is_unlimited_credits": False},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.credits, 80)

    def test_admin_deactivates_and_cannot_delete_self(self):
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            f"/api/v1/admin/users/{self.regular.id}/set-active/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.regular.refresh_from_db()
        self.assertFalse(self.regular.is_active)

        res = self.client.delete(f"/api/v1/admin/users/{self.admin.id}/")
        self.assertEqual(res.status_code, 400)
