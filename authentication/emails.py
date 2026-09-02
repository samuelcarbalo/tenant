"""Envío de correos transaccionales (recuperación de contraseña)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from authentication.email_templates import password_reset_html, user_display_name
from core.email import resend_is_configured, send_system_email

logger = logging.getLogger(__name__)
token_generator = PasswordResetTokenGenerator()


def smtp_is_configured() -> bool:
    if resend_is_configured():
        return True
    return bool(
        getattr(settings, "EMAIL_HOST", "")
        and getattr(settings, "EMAIL_HOST_USER", "")
        and getattr(settings, "EMAIL_HOST_PASSWORD", "")
        and getattr(settings, "DEBUG", False)
    )


def encode_uid(user) -> str:
    return urlsafe_base64_encode(force_bytes(str(user.pk)))


def user_from_uidb64(uidb64: str):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        pk = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=pk, is_active=True)
    except Exception:
        return None


def frontend_public_url() -> str:
    """Base del frontend para enlaces en correos. En producción siempre chever.co."""
    if not getattr(settings, "DEBUG", False):
        return "https://chever.co"
    raw = (getattr(settings, "FRONTEND_URL", None) or "http://localhost:5173").strip().rstrip("/")
    if not raw or "localhost" in raw or "127.0.0.1" in raw:
        return raw or "http://localhost:5173"
    return raw


def build_password_reset_url(user) -> str:
    uid = encode_uid(user)
    token = token_generator.make_token(user)
    return f"{frontend_public_url()}/reset-password/{uid}/{token}/"


def send_password_reset_email(user) -> bool:
    """Envía el enlace de restablecimiento por Resend HTTP. False si el correo no está listo."""
    reset_url = build_password_reset_url(user)
    if not smtp_is_configured():
        logger.error(
            "Correo no configurado: define RESEND_API_KEY en Render. "
            "SMTP está bloqueado (puertos 587/465). No se envió el correo."
        )
        if getattr(settings, "DEBUG", False):
            logger.warning("Enlace de restablecimiento (DEBUG): %s", reset_url)
        return False

    name = user_display_name(user)
    subject = "Restablece tu contraseña en Chéver"
    text = (
        f"Hola {name},\n\n"
        "Recibimos una solicitud para restablecer tu contraseña en Chéver.\n"
        "Abre este enlace (caduca en 24 horas):\n"
        f"{reset_url}\n\n"
        "Si no fuiste tú, puedes ignorar este mensaje.\n"
        "© Chéver. Todos los derechos reservados.\n"
    )
    html = password_reset_html(display_name=name, reset_url=reset_url)
    send_system_email(
        subject,
        text,
        [user.email],
        html=html,
    )
    logger.info("password_reset_email_sent to %s", user.email)
    return True
