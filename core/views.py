import traceback

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from core.email import resend_from_email, resend_is_configured, send_system_email

DEFAULT_TEST_RECIPIENT = "carbal087@gmail.com"
_COOLDOWN_KEY = "smtp_test_email_v1_cooldown"
_COOLDOWN_SECONDS = 45


def _jsonable(result):
    if result is None:
        return None
    if isinstance(result, (dict, list, str, int, float, bool)):
        return result
    if hasattr(result, "id"):
        return {"id": getattr(result, "id", None)}
    return {"result": str(result)}


def _smtp_config_info():
    """Configuración de correo leída en runtime. Nunca incluye secretos."""
    return {
        "transport": "resend_http" if resend_is_configured() else "blocked_smtp",
        "EMAIL_BACKEND": getattr(settings, "EMAIL_BACKEND", None),
        "EMAIL_HOST": getattr(settings, "EMAIL_HOST", None),
        "EMAIL_PORT": getattr(settings, "EMAIL_PORT", None),
        "EMAIL_HOST_USER": getattr(settings, "EMAIL_HOST_USER", None),
        "EMAIL_USE_TLS": getattr(settings, "EMAIL_USE_TLS", False),
        "EMAIL_USE_SSL": getattr(settings, "EMAIL_USE_SSL", False),
        "DEFAULT_FROM_EMAIL": getattr(settings, "DEFAULT_FROM_EMAIL", None),
        "resend_from": resend_from_email() if resend_is_configured() else None,
        "password_configured": bool(getattr(settings, "EMAIL_HOST_PASSWORD", "")),
        "resend_configured": resend_is_configured(),
        "sendgrid_configured": bool(
            getattr(settings, "SENDGRID_API_KEY", "")
            or (getattr(settings, "ANYMAIL", None) or {}).get("SENDGRID_API_KEY")
        ),
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def test_email_api(request):
    """
    Diagnóstico de correo desde el navegador: GET /api/v1/test-email/?email=...
    En producción envía por Resend HTTP (no SMTP).
    """
    recipient = (request.GET.get("email") or DEFAULT_TEST_RECIPIENT).strip()
    config_info = _smtp_config_info()

    if cache.get(_COOLDOWN_KEY):
        return JsonResponse(
            {
                "status": "throttled",
                "message": (
                    f"Espera {_COOLDOWN_SECONDS}s entre pruebas para no saturar el envío."
                ),
                "smtp_config": config_info,
            },
            status=429,
        )

    cache.set(_COOLDOWN_KEY, True, _COOLDOWN_SECONDS)

    try:
        result = send_system_email(
            subject="[Chéver API] Prueba de Envío (Resend HTTP)",
            message=(
                "Si recibes este correo, el envío por HTTPS (Resend) en Render "
                "está funcionando correctamente."
            ),
            recipient_list=[recipient],
        )
        return JsonResponse(
            {
                "status": "success",
                "message": f"Correo enviado exitosamente a {recipient}",
                "provider_result": _jsonable(result),
                "smtp_config": config_info,
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {
                "status": "error",
                "error_type": type(e).__name__,
                "error_details": str(e),
                "traceback": traceback.format_exc(),
                "smtp_config": config_info,
            },
            status=500,
        )
