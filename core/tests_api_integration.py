"""
Suite de integración API — ejecutar:
  python manage.py test core.tests_api_integration --settings=config.settings.development -v 2
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from jobs.models import JobOffer
from moderation.models import ReportePublicacion
from organizations.models import Organization
from payments.models import PaymentOrder, TransaccionFacturacion
from payments.services.payment_processor import apply_approved_payment
from real_estate.models import RealEstateOffer

User = get_user_model()
API = "/api/v1"
TENANT = "conectando-empleo"


def auth_client(user=None):
    client = APIClient()
    client.credentials(HTTP_X_TENANT=TENANT)
    if user:
        client.force_authenticate(user=user)
    return client


class BaseIntegrationTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="CordobaTech Test",
            slug=TENANT,
        )
        self.manager = User.objects.create_user(
            email="manager@test.com",
            username="manager_test",
            password="TestPass123!",
            organization=self.org,
            role="manager",
            company_name="Empresa Test",
            credits=100,
            user_type="company",
        )
        self.user = User.objects.create_user(
            email="user@test.com",
            username="user_test",
            password="TestPass123!",
            organization=self.org,
            role="user",
            credits=10,
        )
        self.anon = auth_client()
        self.manager_client = auth_client(self.manager)
        self.user_client = auth_client(self.user)


class AuthAPITests(BaseIntegrationTestCase):
    def test_login_tenant_user(self):
        res = self.anon.post(
            f"{API}/auth/login/",
            {"email": "user@test.com", "password": "TestPass123!", "organization_slug": TENANT},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

    def test_auth_me(self):
        res = self.user_client.get(f"{API}/auth/me/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["email"], "user@test.com")
        self.assertIn("credits", res.data)


class PaymentsAPITests(BaseIntegrationTestCase):
    def test_packages_public(self):
        res = self.anon.get(f"{API}/payments/packages/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 6)
        ids = {p["id"] for p in res.data}
        self.assertEqual(
            ids, {"basico", "bronce", "plata", "oro", "platino", "diamante"}
        )

    def test_mp_config(self):
        res = self.anon.get(f"{API}/payments/config/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("public_key", res.data)
        self.assertIsInstance(res.data["public_key"], str)

    @patch("payments.views.MercadoPagoService")
    def test_create_preference(self, MockMP):
        mock_instance = MockMP.return_value
        mock_instance.create_preference.return_value = {
            "preference_id": "pref-test-123",
            "init_point": "https://mp.test/checkout",
            "sandbox_init_point": "https://mp.test/sandbox",
        }
        res = self.manager_client.post(
            f"{API}/payments/create-preference/",
            {"package_id": "basico"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["preference_id"], "pref-test-123")
        self.assertTrue(PaymentOrder.objects.filter(user=self.manager, package_id="basico").exists())

    def test_webhook_approves_and_credits(self):
        order = PaymentOrder.objects.create(
            user=self.user,
            package_id="basico",
            credits_amount=20,
            amount_cop=20000,
        )
        with patch("payments.views.MercadoPagoService") as MockMP:
            mock_instance = MockMP.return_value
            mock_instance.get_payment.return_value = {
                "status": "approved",
                "external_reference": str(order.id),
            }
            res = self.anon.post(
                f"{API}/payments/webhook/",
                {"type": "payment", "data": {"id": "12345"}},
                format="json",
            )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.credits, 30)  # 10 + 20
        self.assertTrue(TransaccionFacturacion.objects.filter(payment_order=order).exists())

    def test_billing_breakdown(self):
        order = PaymentOrder.objects.create(
            user=self.user,
            package_id="bronce",
            credits_amount=30,
            amount_cop=28000,
        )
        apply_approved_payment(order, "mp-pay-999")
        tx = TransaccionFacturacion.objects.get(payment_order=order)
        self.assertEqual(tx.monto_total, Decimal("28000"))
        self.assertGreater(tx.comision_mercado_pago, Decimal("0"))
        self.assertGreater(tx.iva_comision, Decimal("0"))
        self.assertLess(tx.monto_neto_recibido, tx.monto_total)


class ModerationAPITests(BaseIntegrationTestCase):
    def setUp(self):
        super().setUp()
        from django.utils import timezone
        from datetime import timedelta

        self.job = JobOffer.objects.create(
            organization=self.org,
            posted_by=self.manager,
            title="Vacante Test",
            company_name="Empresa Test",
            description="Desc",
            expires_at=timezone.now() + timedelta(days=30),
        )

    def test_report_publication(self):
        res = self.user_client.post(
            f"{API}/moderation/reports/",
            {
                "content_type": "job",
                "object_id": str(self.job.id),
                "reason": "fraude",
                "description": "Sospechoso",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

    def test_auto_hide_after_three_reports(self):
        ct = ContentType.objects.get_for_model(JobOffer)
        for i in range(3):
            reporter = User.objects.create_user(
                email=f"rep{i}@test.com",
                username=f"rep{i}",
                password="TestPass123!",
                organization=self.org,
            )
            ReportePublicacion.objects.create(
                reporter=reporter,
                content_type=ct,
                object_id=self.job.id,
                reason="fraude",
            )
        from moderation.services import apply_moderation_if_needed

        apply_moderation_if_needed(ct, self.job.id)
        self.job.refresh_from_db()
        self.assertEqual(self.job.moderation_status, "pendiente_revision")
        self.assertFalse(self.job.is_active)


class JobsRealEstateAPITests(BaseIntegrationTestCase):
    def test_jobs_list_public(self):
        res = self.anon.get(f"{API}/jobs/offers/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_real_estate_list_public(self):
        res = self.anon.get(f"{API}/real-estate/offers/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_create_job_deducts_credits(self):
        initial = self.manager.credits
        from django.utils import timezone
        from datetime import timedelta

        res = self.manager_client.post(
            f"{API}/jobs/offers/",
            {
                "title": "Dev Python",
                "description": "Backend dev",
                "requirements": "Django",
                "location": "Montería",
                "job_type": "full_time",
                "category": "Tecnología",
                "expires_at": (timezone.now() + timedelta(days=30)).isoformat(),
                "status": "published",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.credits, initial - 5)


class NotificationsAPITests(BaseIntegrationTestCase):
    def test_unread_count(self):
        res = self.user_client.get(f"{API}/notifications/unread-count/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("unread_count", res.data)

    def test_list_notifications(self):
        res = self.user_client.get(f"{API}/notifications/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class MessagingAPITests(BaseIntegrationTestCase):
    def test_unread_count(self):
        res = self.user_client.get(f"{API}/messaging/conversations/unread-count/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_list_conversations(self):
        res = self.user_client.get(f"{API}/messaging/conversations/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class SportsAPITests(BaseIntegrationTestCase):
    def test_tournaments_list(self):
        res = self.anon.get(f"{API}/sports/tournaments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class ProfilesAPITests(BaseIntegrationTestCase):
    def test_profiles_me(self):
        from profiles.models import Profile

        Profile.objects.get_or_create(
            user=self.user,
            defaults={"organization": self.org},
        )
        res = self.user_client.get(f"{API}/profiles/me/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
