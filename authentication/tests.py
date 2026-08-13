from django.test import TestCase
from django.contrib.auth import get_user_model

from organizations.models import Organization
from authentication.auth_utils import resolve_login_user
from authentication.serializers import UserLoginSerializer

User = get_user_model()


class PlatformLoginTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="admin@platform.com",
            username="platformadmin",
            password="SecurePass123!",
        )
        self.org = Organization.objects.create(
            name="Test Org",
            slug="test-org",
        )
        self.tenant_user = User.objects.create_user(
            email="user@test.com",
            username="tenantuser",
            password="SecurePass123!",
            organization=self.org,
        )

    def test_superuser_login_without_organization_slug(self):
        user = resolve_login_user("admin@platform.com", "SecurePass123!")
        self.assertIsNotNone(user)
        self.assertTrue(user.is_superuser)
        self.assertIsNone(user.organization_id)

    def test_tenant_user_requires_organization_slug(self):
        user = resolve_login_user("user@test.com", "SecurePass123!")
        self.assertIsNone(user)

        user = resolve_login_user("user@test.com", "SecurePass123!", "test-org")
        self.assertIsNotNone(user)
        self.assertEqual(user.organization, self.org)

    def test_login_serializer_superuser_without_org(self):
        serializer = UserLoginSerializer(
            data={"email": "admin@platform.com", "password": "SecurePass123!"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertTrue(serializer.validated_data["user"].is_superuser)

    def test_login_serializer_tenant_requires_org(self):
        serializer = UserLoginSerializer(
            data={"email": "user@test.com", "password": "SecurePass123!"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("organization_slug", serializer.errors)

    def test_login_serializer_tenant_with_org(self):
        serializer = UserLoginSerializer(
            data={
                "email": "user@test.com",
                "password": "SecurePass123!",
                "organization_slug": "test-org",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_superuser_login_with_tenant_slug_from_pwa(self):
        user = resolve_login_user("admin@platform.com", "SecurePass123!", "test-org")
        self.assertIsNotNone(user)
        self.assertTrue(user.is_superuser)

