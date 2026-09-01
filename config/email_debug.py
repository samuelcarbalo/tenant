"""Diagnóstico de correo temporal (sin Shell de Render)."""

import traceback

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core.email import send_system_email
from core.views import _smtp_config_info

TEST_RECIPIENT = "carbal087@gmail.com"
_COOLDOWN_KEY = "smtp_test_email_cooldown"
_COOLDOWN_SECONDS = 45


@require_GET
def test_email_view(request):
    logs = _smtp_config_info()
    logs["recipient"] = TEST_RECIPIENT
    logs["status"] = "pending"

    if cache.get(_COOLDOWN_KEY):
        logs["status"] = "throttled"
        logs["message"] = (
            f"Espera {_COOLDOWN_SECONDS}s entre pruebas para no saturar el envío."
        )
        return JsonResponse(logs, status=429)

    cache.set(_COOLDOWN_KEY, True, _COOLDOWN_SECONDS)

    try:
        send_system_email(
            subject="Prueba Automática Chéver (Resend HTTP)",
            message="Prueba de envío desencadenada desde el endpoint /api/test-email/.",
            recipient_list=[TEST_RECIPIENT],
        )
        logs["status"] = "success"
        logs["message"] = f"Correo enviado con éxito a {TEST_RECIPIENT}"
        return JsonResponse(logs, status=200)
    except Exception as exc:
        logs["status"] = "error"
        logs["error_details"] = str(exc)
        logs["traceback"] = traceback.format_exc()
        return JsonResponse(logs, status=500)
