import logging

import mercadopago
from django.conf import settings

from payments.packages import get_package

logger = logging.getLogger(__name__)


class MercadoPagoService:
    """Cliente para Mercado Pago Checkout Pro."""

    def __init__(self):
        access_token = getattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "")
        if not access_token or access_token.startswith("YOUR_"):
            logger.warning("MERCADOPAGO_ACCESS_TOKEN no configurado — modo placeholder.")
        self.sdk = mercadopago.SDK(access_token)

    def create_preference(
        self,
        *,
        package_id: str,
        user_email: str,
        user_id: str,
        order_id: str,
    ) -> dict:
        package = get_package(package_id)
        if not package:
            raise ValueError(f"Paquete desconocido: {package_id}")

        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        webhook_url = getattr(settings, "MERCADOPAGO_WEBHOOK_URL", "")
        if not webhook_url:
            webhook_url = f"{getattr(settings, 'BACKEND_URL', 'http://localhost:8000')}/api/v1/payments/webhook/"

        back_urls = {
            "success": f"{frontend_url}/creditos/resultado?status=success",
            "failure": f"{frontend_url}/creditos/resultado?status=failure",
            "pending": f"{frontend_url}/creditos/resultado?status=pending",
        }

        preference_data = {
            "items": [
                {
                    "id": package_id,
                    "title": f"{package['name']} — {package['credits']} créditos CordobaTech",
                    "description": package["description"],
                    "quantity": 1,
                    "currency_id": "COP",
                    "unit_price": float(package["price_cop"]),
                }
            ],
            "payer": {"email": user_email},
            "back_urls": back_urls,
            "external_reference": str(order_id),
            "metadata": {
                "user_id": str(user_id),
                "package_id": package_id,
                "credits": package["credits"],
                "order_id": str(order_id),
            },
        }

        # auto_return exige back_urls HTTPS; en localhost omitirlo
        if frontend_url.startswith("https://"):
            preference_data["auto_return"] = "approved"

        # Webhook solo útil con URL pública (ngrok/producción)
        if webhook_url.startswith("https://"):
            preference_data["notification_url"] = webhook_url

        result = self.sdk.preference().create(preference_data)
        response = result.get("response", {})

        if result.get("status") not in (200, 201):
            logger.error("MP preference error: %s", result)
            raise RuntimeError(response.get("message", "Error al crear preferencia en Mercado Pago"))

        return {
            "preference_id": response.get("id"),
            "init_point": response.get("init_point"),
            "sandbox_init_point": response.get("sandbox_init_point"),
        }

    def get_payment(self, payment_id: str) -> dict:
        result = self.sdk.payment().get(payment_id)
        if result.get("status") != 200:
            raise RuntimeError(f"No se pudo obtener pago {payment_id}")
        return result.get("response", {})
