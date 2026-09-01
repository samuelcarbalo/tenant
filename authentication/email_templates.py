"""Plantillas HTML transaccionales (compatibles con clientes de correo)."""

from __future__ import annotations

from datetime import date
from html import escape

from django.conf import settings

# Navy / teal de la marca. El wordmark oficial es negro: va sobre placa blanca.
NAVY = "#021433"
NAVY_DEEP = "#001332"
TEAL = "#0BAD9A"
EMERALD = "#34d399"
MUTED = "#94a3b8"
WHITE = "#ffffff"

DEFAULT_LOGO_URL = "https://chever.co/chever_oficial.svg"


def email_logo_url() -> str:
    explicit = (getattr(settings, "EMAIL_LOGO_URL", None) or "").strip()
    if explicit:
        return explicit
    # Wordmark ya publicado. PNG opcional: EMAIL_LOGO_URL=https://chever.co/assets/logo.png
    return DEFAULT_LOGO_URL


def user_display_name(user) -> str:
    full = (getattr(user, "full_name", None) or "").strip()
    first = (getattr(user, "first_name", None) or "").strip()
    if first:
        return first
    if full and "@" not in full:
        return full.split()[0]
    email = (getattr(user, "email", None) or "").strip()
    local = email.split("@")[0] if email else ""
    return local or "usuario"


def password_reset_html(*, display_name: str, reset_url: str) -> str:
    name = escape(display_name)
    url = escape(reset_url, quote=True)
    logo = escape(email_logo_url(), quote=True)
    year = date.today().year
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="dark" />
  <title>Restablece tu contraseña en Chéver</title>
</head>
<body style="margin:0;padding:0;background:{NAVY};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{NAVY};">
    <tr>
      <td align="center" style="padding:32px 12px;">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;background:{NAVY_DEEP};border:1px solid #0bad9a55;border-radius:20px;overflow:hidden;">
          <tr>
            <td align="center" style="background:{TEAL};padding:28px 24px;">
              <table role="presentation" cellpadding="0" cellspacing="0" style="background:{WHITE};border-radius:14px;">
                <tr>
                  <td style="padding:10px 18px;">
                    <img src="{logo}" alt="Chéver" width="180" height="48" style="display:block;width:180px;max-width:180px;height:auto;border:0;" />
                  </td>
                </tr>
              </table>
              <p style="margin:14px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:{NAVY};">
                Córdoba · Comercio · Deporte
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:36px 32px 16px;font-family:Arial,Helvetica,sans-serif;color:{WHITE};">
              <p style="margin:0 0 8px;font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:{TEAL};">
                Seguridad de la cuenta
              </p>
              <h1 style="margin:0 0 16px;font-size:26px;line-height:1.25;font-weight:800;color:{WHITE};">
                Hola {name}
              </h1>
              <p style="margin:0 0 16px;font-size:16px;line-height:1.6;color:#e2e8f0;">
                Recibimos una solicitud para restablecer la contraseña de tu cuenta en
                <strong style="color:{EMERALD};">Chéver</strong>.
                El enlace caduca en 24 horas.
              </p>
              <p style="margin:0 0 28px;font-size:15px;line-height:1.6;color:{MUTED};">
                Si no fuiste tú, puedes ignorar este mensaje. Tu contraseña no cambiará.
              </p>
              <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto 28px;">
                <tr>
                  <td align="center" bgcolor="{EMERALD}" style="border-radius:999px;background:{EMERALD};">
                    <a href="{url}" target="_blank" style="display:inline-block;padding:16px 36px;font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:800;color:{NAVY};text-decoration:none;border-radius:999px;">
                      Restablecer contraseña
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0;font-size:12px;line-height:1.5;color:{MUTED};word-break:break-all;">
                Si el botón no funciona, copia este enlace:<br />
                <a href="{url}" style="color:{TEAL};text-decoration:underline;">{url}</a>
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 32px 32px;border-top:1px solid #0bad9a33;font-family:Arial,Helvetica,sans-serif;text-align:center;">
              <p style="margin:0 0 6px;font-size:12px;color:{MUTED};">
                © {year} Chéver. Todos los derechos reservados.
              </p>
              <p style="margin:0;font-size:12px;color:#64748b;">
                Montelíbano, Córdoba · <a href="https://chever.co" style="color:{TEAL};text-decoration:none;">chever.co</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
