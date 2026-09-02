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
