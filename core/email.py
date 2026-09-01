"""Envío de correo del sistema: Resend por HTTPS (puerto 443), sin smtplib."""

from __future__ import annotations

import os
from html import escape

from django.conf import settings
from django.core.mail import send_mail

RESEND_ONBOARDING_FROM = "Chéver <onboarding@resend.dev>"


def _resend_api_key() -> str:
    return (
        os.getenv("RESEND_API_KEY")
        or getattr(settings, "RESEND_API_KEY", "")
        or ""
    ).strip()


def resend_is_configured() -> bool:
    return bool(_resend_api_key())


def resend_from_email() -> str:
    explicit = (os.getenv("RESEND_FROM_EMAIL") or "").strip()
    if explicit:
        return explicit
    current = (getattr(settings, "DEFAULT_FROM_EMAIL", None) or "").strip()
    lowered = current.lower()
    if current and "gmail.com" not in lowered and "googlemail.com" not in lowered:
        return current
    return RESEND_ONBOARDING_FROM


def send_system_email(subject, message, recipient_list, html=None):
    """
    Envía correo por la API HTTP de Resend si RESEND_API_KEY está definida.
    En Render Free SMTP (587/465) está bloqueado; no usar smtplib allí.
    """
    resend_api_key = _resend_api_key()

    if resend_api_key:
        import resend

        resend.api_key = resend_api_key
        html_body = html if html else f"<p>{escape(message).replace(chr(10), '<br>')}</p>"
        params = {
            "from": resend_from_email(),
            "to": list(recipient_list),
            "subject": subject,
            "html": html_body,
            "text": message,
        }
        return resend.Emails.send(params)

    if not getattr(settings, "DEBUG", False):
        raise RuntimeError(
            "RESEND_API_KEY no está configurada. Render bloquea SMTP "
            "(Errno 101 en 587 y 465). Agrega RESEND_API_KEY en el dashboard "
            "y un remitente verificado (o usa onboarding@resend.dev en pruebas)."
        )

    return send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
        fail_silently=False,
    )
