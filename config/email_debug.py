"""Diagnóstico SMTP temporal (sin Shell de Render). Quitar cuando el correo funcione."""

import traceback

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.http import require_GET

TEST_RECIPIENT = "carbal087@gmail.com"
_COOLDOWN_KEY = "smtp_test_email_cooldown"
_COOLDOWN_SECONDS = 45


@require_GET
def test_email_view(request):
    logs = {
        "status": "pending",
        "smtp_host": getattr(settings, "EMAIL_HOST", "No configurado"),
        "smtp_port": getattr(settings, "EMAIL_PORT", "No configurado"),
        "smtp_user": getattr(settings, "EMAIL_HOST_USER", "No configurado") or "No configurado",
        "smtp_from": getattr(settings, "DEFAULT_FROM_EMAIL", "No configurado"),
        "smtp_backend": getattr(settings, "EMAIL_BACKEND", "No configurado"),
        "use_tls": getattr(settings, "EMAIL_USE_TLS", False),
        "use_ssl": getattr(settings, "EMAIL_USE_SSL", False),
        "password_configured": bool(getattr(settings, "EMAIL_HOST_PASSWORD", "")),
        "recipient": TEST_RECIPIENT,
    }

    if cache.get(_COOLDOWN_KEY):
        logs["status"] = "throttled"
        logs["message"] = (
            f"Espera {_COOLDOWN_SECONDS}s entre pruebas para no saturar SMTP."
        )
        return JsonResponse(logs, status=429)

    cache.set(_COOLDOWN_KEY, True, _COOLDOWN_SECONDS)

    try:
        send_mail(
            subject="Prueba Automática SMTP Chéver",
            message="Prueba de envío desencadenada desde el endpoint /api/test-email/.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[TEST_RECIPIENT],
            fail_silently=False,
        )
        logs["status"] = "success"
        logs["message"] = f"Correo enviado con éxito a {TEST_RECIPIENT}"
        return JsonResponse(logs, status=200)
    except Exception as exc:
        logs["status"] = "error"
        logs["error_details"] = str(exc)
        logs["traceback"] = traceback.format_exc()
        return JsonResponse(logs, status=500)
