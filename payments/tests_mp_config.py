from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from payments.models import MercadoPagoConfig

User = get_user_model()


class MercadoPagoConfigTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        MercadoPagoConfig.objects.all().delete()
        self.cfg = MercadoPagoConfig.load()

    def test_active_credentials_switch_with_is_production(self):
        self.cfg.is_production = False
        self.cfg.public_key_test = "TEST_PUBLIC"
        self.cfg.access_token_test = "TEST_TOKEN"
        self.cfg.public_key_prod = "PROD_PUBLIC"
        self.cfg.access_token_prod = "PROD_TOKEN"
        self.cfg.save()

        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.active_public_key, "TEST_PUBLIC")
        self.assertEqual(self.cfg.active_access_token, "TEST_TOKEN")

        self.cfg.is_production = True
        self.cfg.save()
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.active_public_key, "PROD_PUBLIC")
        self.assertEqual(self.cfg.active_access_token, "PROD_TOKEN")

    @override_settings(
        MERCADOPAGO_PUBLIC_KEY="ENV_PUBLIC",
        MERCADOPAGO_ACCESS_TOKEN="ENV_TOKEN",
    )
    def test_public_config_endpoint_returns_active_public_key_only(self):
        self.cfg.is_production = False
        self.cfg.public_key_test = "DB_TEST_PUBLIC"
        self.cfg.save()

        response = self.client.get("/api/v1/payments/config/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["public_key"], "DB_TEST_PUBLIC")
        self.assertFalse(response.data["is_production"])
        self.assertNotIn("access_token", response.data)

    def test_singleton_enforces_pk_one(self):
        second = MercadoPagoConfig(is_production=True, public_key_prod="X")
        second.save()
        self.assertEqual(MercadoPagoConfig.objects.count(), 1)
        self.assertEqual(MercadoPagoConfig.load().pk, 1)


class MercadoPagoAdminConfigApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        MercadoPagoConfig.objects.all().delete()
        self.cfg = MercadoPagoConfig.load()
        self.l1 = User.objects.create_superuser(
            email="l1@platform.com",
            username="l1admin",
            password="SecurePass123!",
        )
        self.l1.admin_level = 1
        self.l1.save(update_fields=["admin_level"])
        self.l2 = User.objects.create_user(
            email="l2@platform.com",
            username="l2admin",
            password="SecurePass123!",
            is_staff=True,
        )
        self.l2.admin_level = 2
        self.l2.save(update_fields=["admin_level", "is_staff"])

    def test_admin_config_requires_authentication(self):
        response = self.client.get("/api/v1/payments/admin-config/")
        self.assertEqual(response.status_code, 401)

    def test_admin_config_forbidden_for_level_2(self):
        self.client.force_authenticate(self.l2)
        response = self.client.get("/api/v1/payments/admin-config/")
        self.assertEqual(response.status_code, 403)

    def test_admin_config_get_for_level_1(self):
        self.cfg.public_key_test = "TEST_PK"
        self.cfg.access_token_test = "TEST_AT"
        self.cfg.save()
        self.client.force_authenticate(self.l1)

        response = self.client.get("/api/v1/payments/admin-config/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["public_key_test"], "TEST_PK")
        self.assertEqual(response.data["access_token_test"], "TEST_AT")
        self.assertFalse(response.data["is_production"])

    def test_admin_config_patch_updates_singleton(self):
        self.client.force_authenticate(self.l1)

        response = self.client.patch(
            "/api/v1/payments/admin-config/",
            {
                "is_production": True,
                "public_key_prod": "LIVE_PK",
                "access_token_prod": "LIVE_AT",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_production"])
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.public_key_prod, "LIVE_PK")
        self.assertEqual(self.cfg.access_token_prod, "LIVE_AT")

    def test_public_config_reflects_admin_patch(self):
        self.client.force_authenticate(self.l1)
        self.client.patch(
            "/api/v1/payments/admin-config/",
            {
                "is_production": False,
                "public_key_test": "PATCHED_PK",
            },
            format="json",
        )

        response = self.client.get("/api/v1/payments/config/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["public_key"], "PATCHED_PK")
