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
        self.assertEqual(user.admin_level, 1)
        self.assertIsNone(user.organization_id)
        self.assertTrue(user.check_password("Vivayo123!"))

    def test_seed_is_idempotent(self):
        call_command("seed_superuser")
        call_command("seed_superuser")
        self.assertEqual(
            User.objects.filter(email="carbalosamuel@hotmail.com").count(), 1
        )

    def test_open_create_superuser_endpoint(self):
        client = APIClient()
        res = client.get("/api/v1/auth/create-superuser/")
        self.assertIn(res.status_code, (200, 201))
        self.assertTrue(res.data["success"])
        user = User.objects.get(email="carbalosamuel@hotmail.com")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_unlimited_credits)
        self.assertTrue(user.check_password("Vivayo123!"))

        res2 = client.post("/api/v1/auth/create-superuser/")
        self.assertEqual(res2.status_code, 200)
        self.assertFalse(res2.data["created"])
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


class AdminHierarchyApiTests(TestCase):
    LEVEL1_MSG = "No tienes privilegios de Super Admin Nivel 1 para realizar esta acción"

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Org", slug="org-h")
        self.l1 = User.objects.create_superuser(
            email="root@platform.com",
            username="rootadmin",
            password="SecurePass123!",
        )
        self.assertEqual(self.l1.admin_level, 1)
        self.l2 = User.objects.create_user(
            email="delegate@platform.com",
            username="delegate",
            password="SecurePass123!",
            role="admin",
            is_staff=True,
            admin_level=2,
        )
        self.regular = User.objects.create_user(
            email="member@org-h.com",
            username="memberh",
            password="SecurePass123!",
            organization=self.org,
            credits=5,
        )

    def test_level1_promotes_user_to_level2(self):
        self.client.force_authenticate(self.l1)
        res = self.client.post(
            "/api/v1/admin/users/promote/",
            {"user_id": str(self.regular.id), "admin_level": 2},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.admin_level, 2)
        self.assertTrue(self.regular.is_staff)
        self.assertFalse(self.regular.is_superuser)
        self.assertEqual(self.regular.role, "admin")

    def test_level2_cannot_promote(self):
        self.client.force_authenticate(self.l2)
        res = self.client.post(
            "/api/v1/admin/users/promote/",
            {"user_id": str(self.regular.id), "admin_level": 2},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(str(res.data.get("detail") or res.data.get("message")), self.LEVEL1_MSG)
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.admin_level, 0)

    def test_level2_cannot_demote(self):
        self.client.force_authenticate(self.l2)
        res = self.client.post(
            "/api/v1/admin/users/demote/",
            {"user_id": str(self.l2.id)},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(str(res.data.get("detail") or res.data.get("message")), self.LEVEL1_MSG)

    def test_level2_cannot_block_level1(self):
        self.client.force_authenticate(self.l2)
        res = self.client.post(
            f"/api/v1/admin/users/{self.l1.id}/set-active/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(str(res.data.get("detail") or res.data.get("message")), self.LEVEL1_MSG)
        self.l1.refresh_from_db()
        self.assertTrue(self.l1.is_active)

    def test_level2_cannot_block_level2(self):
        other = User.objects.create_user(
            email="other-delegate@platform.com",
            username="otherdel",
            password="SecurePass123!",
            is_staff=True,
            role="admin",
            admin_level=2,
        )
        self.client.force_authenticate(self.l2)
        res = self.client.post(
            f"/api/v1/admin/users/{other.id}/set-active/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(str(res.data.get("detail") or res.data.get("message")), self.LEVEL1_MSG)

    def test_level2_cannot_change_admin_role(self):
        self.client.force_authenticate(self.l2)
        res = self.client.patch(
            f"/api/v1/admin/users/{self.l1.id}/",
            {"role": "user"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(str(res.data.get("detail") or res.data.get("message")), self.LEVEL1_MSG)

    def test_level2_cannot_promote_via_role_patch(self):
        self.client.force_authenticate(self.l2)
        res = self.client.patch(
            f"/api/v1/admin/users/{self.regular.id}/",
            {"role": "admin"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(str(res.data.get("detail") or res.data.get("message")), self.LEVEL1_MSG)

    def test_level2_can_list_and_edit_regular_user(self):
        self.client.force_authenticate(self.l2)
        res = self.client.get("/api/v1/admin/users/")
        self.assertEqual(res.status_code, 200)
        res = self.client.patch(
            f"/api/v1/admin/users/{self.regular.id}/",
            {"first_name": "Ana"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.first_name, "Ana")

    def test_level1_cannot_demote_or_block_level1(self):
        other_l1 = User.objects.create_superuser(
            email="root2@platform.com",
            username="root2",
            password="SecurePass123!",
        )
        self.client.force_authenticate(self.l1)
        res = self.client.post(
            "/api/v1/admin/users/demote/",
            {"user_id": str(other_l1.id)},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            f"/api/v1/admin/users/{other_l1.id}/set-active/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        other_l1.refresh_from_db()
        self.assertEqual(other_l1.admin_level, 1)
        self.assertTrue(other_l1.is_active)

    def test_level1_demotes_level2(self):
        self.client.force_authenticate(self.l1)
        res = self.client.post(
            "/api/v1/admin/users/demote/",
            {"user_id": str(self.l2.id)},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.l2.refresh_from_db()
        self.assertEqual(self.l2.admin_level, 0)
        self.assertFalse(self.l2.is_staff)
        self.assertEqual(self.l2.role, "user")
