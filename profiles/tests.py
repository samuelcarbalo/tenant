from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from organizations.models import Organization
from profiles.models import Profile

User = get_user_model()


class ProfilePatchTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Chever Org",
            slug="chever-org",
            description="",
        )
        self.user = User.objects.create_user(
            email="perfil@chever.co",
            username="perfil",
            password="secret123",
            organization=self.organization,
            first_name="Antes",
            last_name="Usuario",
        )
        self.profile = Profile.objects.create(
            user=self.user,
            organization=self.organization,
            bio="Bio inicial",
            location="Montería",
            department="Tech",
            job_title="Dev",
            birth_date=date(1990, 5, 15),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_patch_persists_profile_fields_and_returns_full_payload(self):
        payload = {
            "user_name": "María López",
            "bio": "Nueva bio",
            "location": "Chever, Córdoba",
            "department": "Producto",
            "job_title": "PM",
            "birth_date": "1992-08-20",
        }

        response = self.client.patch(
            f"/api/v1/profiles/{self.profile.id}/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["bio"], "Nueva bio")
        self.assertEqual(response.data["location"], "Chever, Córdoba")
        self.assertEqual(response.data["department"], "Producto")
        self.assertEqual(response.data["job_title"], "PM")
        self.assertEqual(response.data["birth_date"], "1992-08-20")
        self.assertEqual(response.data["user_name"], "María López")
        self.assertEqual(response.data["id"], str(self.profile.id))

        self.profile.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.profile.bio, "Nueva bio")
        self.assertEqual(self.profile.location, "Chever, Córdoba")
        self.assertEqual(self.profile.department, "Producto")
        self.assertEqual(self.profile.job_title, "PM")
        self.assertEqual(str(self.profile.birth_date), "1992-08-20")
        self.assertEqual(self.user.first_name, "María")
        self.assertEqual(self.user.last_name, "López")

    def test_profiles_me_returns_saved_values(self):
        self.profile.bio = "Persistido"
        self.profile.location = "Lorica"
        self.profile.save(update_fields=["bio", "location"])

        response = self.client.get("/api/v1/profiles/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["bio"], "Persistido")
        self.assertEqual(response.data["location"], "Lorica")
