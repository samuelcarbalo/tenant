from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from authentication.terms import CURRENT_TERMS_VERSION
from organizations.models import Organization


class TermsAcceptanceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        Organization.objects.create(name="Org Legal", slug="org-legal")
        self.payload = {
            "email": "legal@test.com",
            "username": "legaluser",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "Ana",
            "last_name": "Legal",
            "organization_slug": "org-legal",
            "user_type": "person",
        }

    def test_register_rejects_missing_terms(self):
        response = self.client.post("/api/v1/auth/register/", self.payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_register_stores_terms_version(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {**self.payload, "accepted_terms": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(email="legal@test.com")
        self.assertTrue(user.accepted_terms)
        self.assertEqual(user.terms_version, CURRENT_TERMS_VERSION)
        self.assertIsNotNone(user.terms_accepted_at)

    def test_accept_terms_updates_outdated_version(self):
        org = Organization.objects.create(name="Org Acepta", slug="org-acepta")
        user = User.objects.create_user(
            email="viejo@test.com",
            username="viejo",
            password="SecurePass123!",
            organization=org,
            accepted_terms=True,
            terms_version="2020-01-01",
        )
        self.client.force_authenticate(user=user)
        response = self.client.post("/api/v1/auth/accept-terms/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        user.refresh_from_db()
        self.assertEqual(user.terms_version, CURRENT_TERMS_VERSION)
        self.assertIsNotNone(user.terms_accepted_at)
