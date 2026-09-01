import traceback

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

DEFAULT_TEST_RECIPIENT = "carbal087@gmail.com"
_COOLDOWN_KEY = "smtp_test_email_v1_cooldown"
_COOLDOWN_SECONDS = 45


def _smtp_config_info():
    """Configuración SMTP leída en runtime. Nunca incluye EMAIL_HOST_PASSWORD."""
    return {
        "EMAIL_BACKEND": getattr(settings, "EMAIL_BACKEND", None),
        "EMAIL_HOST": getattr(settings, "EMAIL_HOST", None),
        "EMAIL_PORT": getattr(settings, "EMAIL_PORT", None),
        "EMAIL_HOST_USER": getattr(settings, "EMAIL_HOST_USER", None),
        "EMAIL_USE_TLS": getattr(settings, "EMAIL_USE_TLS", False),
        "EMAIL_USE_SSL": getattr(settings, "EMAIL_USE_SSL", False),
        "DEFAULT_FROM_EMAIL": getattr(settings, "DEFAULT_FROM_EMAIL", None),
        "password_configured": bool(getattr(settings, "EMAIL_HOST_PASSWORD", "")),
        "resend_configured": bool(
            getattr(settings, "RESEND_API_KEY", "")
            or (getattr(settings, "ANYMAIL", None) or {}).get("RESEND_API_KEY")
        ),
        "sendgrid_configured": bool(
            getattr(settings, "SENDGRID_API_KEY", "")
            or (getattr(settings, "ANYMAIL", None) or {}).get("SENDGRID_API_KEY")
        ),
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def test_email_api(request):
    """
    Diagnóstico SMTP desde el navegador: GET /api/v1/test-email/?email=...
    Intenta send_mail y devuelve éxito o la traza completa del error.
    """
    recipient = (request.GET.get("email") or DEFAULT_TEST_RECIPIENT).strip()
    config_info = _smtp_config_info()

    if cache.get(_COOLDOWN_KEY):
        return JsonResponse(
            {
                "status": "throttled",
                "message": (
                    f"Espera {_COOLDOWN_SECONDS}s entre pruebas para no saturar SMTP."
                ),
                "smtp_config": config_info,
            },
            status=429,
        )

    cache.set(_COOLDOWN_KEY, True, _COOLDOWN_SECONDS)

    try:
        sent_count = send_mail(
            subject="[Chéver API] Prueba de Envío SMTP",
            message=(
                "Si recibes este correo, la configuración SMTP en Render "
                "está funcionando correctamente."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return JsonResponse(
            {
                "status": "success",
                "message": f"Correo enviado exitosamente a {recipient}",
                "emails_sent": sent_count,
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
