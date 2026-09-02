
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from payments.models import MercadoPagoConfig

User = get_user_model()


class MercadoPagoConfigAdminTests(TestCase):
    def setUp(self):
        MercadoPagoConfig.objects.all().delete()
        self.admin = User.objects.create_superuser(
            username="admin_mp",
            email="admin_mp@example.com",
            password="adminpass123",
        )
        self.client.force_login(self.admin)

    def test_changelist_redirects_to_singleton_change_form(self):
        MercadoPagoConfig.load()

        response = self.client.get(reverse("admin:payments_mercadopagoconfig_changelist"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("admin:payments_mercadopagoconfig_change", args=(1,)),
        )

    def test_change_form_shows_is_production_switch(self):
        cfg = MercadoPagoConfig.load()

        response = self.client.get(
            reverse("admin:payments_mercadopagoconfig_change", args=(cfg.pk,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is_production")
        self.assertContains(response, "public_key_test")
        self.assertContains(response, "access_token_prod")

    def test_has_add_permission_blocked_when_singleton_exists(self):
        MercadoPagoConfig.load()

        response = self.client.get(reverse("admin:payments_mercadopagoconfig_add"))

        self.assertIn(response.status_code, (403, 302))
