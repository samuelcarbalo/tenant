"""Envío de correos transaccionales (recuperación de contraseña)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import EmailMultiAlternatives
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

logger = logging.getLogger(__name__)
token_generator = PasswordResetTokenGenerator()


def smtp_is_configured() -> bool:
    backend = getattr(settings, "EMAIL_BACKEND", "") or ""
    if "anymail" in backend or "mail_backends" in backend:
        anymail = getattr(settings, "ANYMAIL", None) or {}
        return bool(
            getattr(settings, "RESEND_API_KEY", "")
            or getattr(settings, "SENDGRID_API_KEY", "")
            or anymail.get("RESEND_API_KEY")
            or anymail.get("SENDGRID_API_KEY")
        )
    return bool(
        getattr(settings, "EMAIL_HOST", "")
        and getattr(settings, "EMAIL_HOST_USER", "")
        and getattr(settings, "EMAIL_HOST_PASSWORD", "")
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


def build_password_reset_url(user) -> str:
    frontend = (getattr(settings, "FRONTEND_URL", None) or "https://chever.co").rstrip("/")
    uid = encode_uid(user)
    token = token_generator.make_token(user)
    return f"{frontend}/recuperar-contrasena?uid={uid}&token={token}"


def send_password_reset_email(user) -> bool:
    """Envía el enlace de restablecimiento. False si SMTP no está listo o falla el envío."""
    reset_url = build_password_reset_url(user)
    if not smtp_is_configured():
        logger.error(
            "Correo no configurado: define SMTP (EMAIL_HOST_USER + "
            "EMAIL_HOST_PASSWORD) o RESEND_API_KEY. No se envió el correo."
        )
        if getattr(settings, "DEBUG", False):
            logger.warning("Enlace de restablecimiento (DEBUG): %s", reset_url)
        return False

    name = getattr(user, "full_name", "") or user.email
    subject = "Restablece tu contraseña en Chéver"
    text = (
        f"Hola {name},\n\n"
        "Recibimos una solicitud para restablecer tu contraseña en Chéver.\n"
        "Abre este enlace (caduca en 24 horas):\n"
        f"{reset_url}\n\n"
        "Si no fuiste tú, puedes ignorar este mensaje.\n"
    )
    html = f"""
    <p>Hola {name},</p>
    <p>Recibimos una solicitud para restablecer tu contraseña en <strong>Chéver</strong>.</p>
    <p><a href="{reset_url}">Restablecer contraseña</a></p>
    <p>El enlace caduca en 24 horas. Si no fuiste tú, ignora este mensaje.</p>
    """
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=False)
    logger.info("password_reset_email_sent to %s", user.email)
    return True
