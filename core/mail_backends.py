"""Envío de correo por HTTPS (Resend). Evita smtplib en redes que bloquean 587/465."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _resend_api_key() -> str:
    key = (getattr(settings, "RESEND_API_KEY", None) or "").strip()
    if key:
        return key
    anymail = getattr(settings, "ANYMAIL", None) or {}
    return (anymail.get("RESEND_API_KEY") or "").strip()


class ResendHTTPEmailBackend(BaseEmailBackend):
    """POST https://api.resend.com/emails — no usa el puerto SMTP de Gmail."""

    def send_messages(self, email_messages):
        api_key = _resend_api_key()
        if not api_key:
            raise RuntimeError(
                "RESEND_API_KEY no está configurada. "
                "En Render Free el SMTP (587/465) suele estar bloqueado; "
                "define RESEND_API_KEY para enviar por HTTPS."
            )

        sent = 0
        for message in email_messages:
            payload = {
                "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                "to": list(message.to),
                "subject": message.subject or "",
                "text": message.body or "",
            }
            if message.cc:
                payload["cc"] = list(message.cc)
            if message.bcc:
                payload["bcc"] = list(message.bcc)
            html = None
            if getattr(message, "alternatives", None):
                for content, mimetype in message.alternatives:
                    if mimetype == "text/html":
                        html = content
                        break
            if html:
                payload["html"] = html

            request = Request(
                RESEND_ENDPOINT,
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=20) as response:
                    if getattr(response, "status", 200) >= 400:
                        raise RuntimeError(
                            response.read().decode("utf-8", errors="replace")
                        )
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Resend HTTP {exc.code}: {body}") from exc
            except URLError as exc:
                raise RuntimeError(f"Resend no alcanzable: {exc}") from exc
            sent += 1
        return sent
