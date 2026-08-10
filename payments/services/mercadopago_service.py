import logging
from urllib.parse import urlparse

import mercadopago
from django.conf import settings

from payments.packages import get_package

logger = logging.getLogger(__name__)


def _normalize_public_origin(url: str) -> str:
    """
    Normaliza a origin https://host (sin path/query).
    MP rechaza HTTP y URLs mal formadas en back_urls / notification_url.
    """
    raw = (url or "").strip().strip("'\"")
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    # Quita paths accidentales (ej. https://sitio.com/login)
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _require_https_origin(url: str, *, setting_name: str) -> str:
    origin = _normalize_public_origin(url)
    if not origin.startswith("https://"):
        raise ValueError(
            f"{setting_name} debe ser una URL HTTPS pública "
            f"(ej. https://capisjdigital.site). Valor actual: {url!r}"
        )
    host = urlparse(origin).hostname or ""
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        raise ValueError(
            f"{setting_name} no puede ser localhost: Mercado Pago exige HTTPS "
            f"con dominio público en back_urls. Valor actual: {url!r}"
        )
    return origin


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

        frontend_url = _require_https_origin(
            getattr(settings, "FRONTEND_URL", ""),
            setting_name="FRONTEND_URL",
        )
        webhook_url = (getattr(settings, "MERCADOPAGO_WEBHOOK_URL", "") or "").strip().rstrip("/")
        if not webhook_url:
            backend = _normalize_public_origin(getattr(settings, "BACKEND_URL", ""))
            if backend.startswith("https://"):
                webhook_url = f"{backend}/api/v1/payments/webhook/"
        if webhook_url and not webhook_url.startswith("https://"):
            logger.warning("MERCADOPAGO_WEBHOOK_URL no es HTTPS; se omite notification_url")
            webhook_url = ""

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
            "auto_return": "approved",
            "external_reference": str(order_id),
            "metadata": {
                "user_id": str(user_id),
                "package_id": package_id,
                "credits": package["credits"],
                "order_id": str(order_id),
            },
        }

        if webhook_url.startswith("https://"):
            preference_data["notification_url"] = webhook_url

        result = self.sdk.preference().create(preference_data)
        response = result.get("response", {})

        if result.get("status") not in (200, 201):
            logger.error(
                "MP preference error: %s | back_urls=%s notification_url=%s",
                result,
                back_urls,
                preference_data.get("notification_url"),
            )
            message = response.get("message") or response.get("error") or "Error al crear preferencia en Mercado Pago"
            raise RuntimeError(message)

        return {
            "preference_id": response.get("id"),
            "init_point": response.get("init_point"),
            "sandbox_init_point": response.get("sandbox_init_point"),
        }

    def create_preference_from_items(
        self,
        *,
        items: list[dict],
        user_email: str,
        user_id: str,
        order_id: str,
        order_type: str = "ecommerce",
        back_path: str = "/tienda/resultado",
        metadata: dict | None = None,
    ) -> dict:
        """Preferencia genérica (tienda u otros) reutilizando back_urls / webhook HTTPS."""
        if not items:
            raise ValueError("items vacío")

        frontend_url = _require_https_origin(
            getattr(settings, "FRONTEND_URL", ""),
            setting_name="FRONTEND_URL",
        )
        webhook_url = (getattr(settings, "MERCADOPAGO_WEBHOOK_URL", "") or "").strip().rstrip("/")
        if not webhook_url:
            backend = _normalize_public_origin(getattr(settings, "BACKEND_URL", ""))
            if backend.startswith("https://"):
                webhook_url = f"{backend}/api/v1/payments/webhook/"
        if webhook_url and not webhook_url.startswith("https://"):
            webhook_url = ""

        path = back_path if back_path.startswith("/") else f"/{back_path}"
        back_urls = {
            "success": f"{frontend_url}{path}?status=success",
            "failure": f"{frontend_url}{path}?status=failure",
            "pending": f"{frontend_url}{path}?status=pending",
        }

        meta = {
            "user_id": str(user_id),
            "order_id": str(order_id),
            "order_type": order_type,
        }
        if metadata:
            meta.update(metadata)

        preference_data = {
            "items": items,
            "payer": {"email": user_email},
            "back_urls": back_urls,
            "auto_return": "approved",
            "external_reference": str(order_id),
            "metadata": meta,
        }
        if webhook_url.startswith("https://"):
            preference_data["notification_url"] = webhook_url

        result = self.sdk.preference().create(preference_data)
        response = result.get("response", {})
        if result.get("status") not in (200, 201):
            logger.error("MP preference (items) error: %s", result)
            message = (
                response.get("message")
                or response.get("error")
                or "Error al crear preferencia en Mercado Pago"
            )
            raise RuntimeError(message)

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
