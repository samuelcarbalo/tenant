from django.test import Client, TestCase


class HealthzTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_healthz_get_returns_json_healthy(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})

    def test_healthz_head_returns_200_without_body(self):
        response = self.client.head("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    def test_api_v1_health_alias(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})
