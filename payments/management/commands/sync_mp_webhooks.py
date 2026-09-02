"""
Lista y registra webhooks de Mercado Pago vía API REST.

Uso:
  python manage.py sync_mp_webhooks --list
  python manage.py sync_mp_webhooks --ensure
  python manage.py sync_mp_webhooks --ensure --url https://missingdigitalback.onrender.com/api/v1/payments/webhook/

Requiere MERCADOPAGO_ACCESS_TOKEN en el entorno.
El secreto del webhook (firma) se configura en el panel de MP o se guarda
en MERCADOPAGO_WEBHOOK_SECRET tras crear la suscripción.
"""

from __future__ import annotations

import json

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

MP_API = "https://api.mercadopago.com"


class Command(BaseCommand):
    help = "Consulta / crea la suscripción de webhooks de Mercado Pago"

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true", help="Listar webhooks existentes")
        parser.add_argument(
            "--ensure",
            action="store_true",
            help="Crear webhook si no existe la URL configurada",
        )
        parser.add_argument(
            "--url",
            type=str,
            default="",
            help="URL del webhook (default: settings.MERCADOPAGO_WEBHOOK_URL)",
        )
        parser.add_argument(
            "--events",
            type=str,
            default="payment,merchant_order",
            help="Tópicos separados por coma (default: payment,merchant_order)",
        )

    def handle(self, *args, **options):
        token = getattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "")
        if not token or token.startswith("YOUR_"):
            raise CommandError("Configura MERCADOPAGO_ACCESS_TOKEN en el entorno.")

        webhook_url = (options["url"] or getattr(settings, "MERCADOPAGO_WEBHOOK_URL", "")).rstrip("/")
        if options["ensure"] and not webhook_url:
            raise CommandError("Debes pasar --url o definir MERCADOPAGO_WEBHOOK_URL.")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # 1) Listar
        self.stdout.write(self.style.NOTICE("Consultando webhooks en Mercado Pago…"))
        resp = requests.get(f"{MP_API}/v1/webhooks", headers=headers, timeout=30)
        if resp.status_code >= 400:
            # Algunas cuentas usan /v1/webhooks/ tipado distinto; intentar endpoint de applications
            self.stdout.write(
                self.style.WARNING(
                    f"GET /v1/webhooks → {resp.status_code}: {resp.text[:400]}\n"
                    "Si tu cuenta usa el panel de 'Tus integraciones', crea el webhook allí "
                    "y copia el secreto a MERCADOPAGO_WEBHOOK_SECRET."
                )
            )
            existing = []
        else:
            body = resp.json()
            existing = body if isinstance(body, list) else body.get("results") or body.get("data") or []
            self.stdout.write(json.dumps(existing, indent=2, ensure_ascii=False))

        if options["list"] and not options["ensure"]:
            return

        if not options["ensure"]:
            self.stdout.write("Usa --ensure para crear el webhook si falta.")
            return

        # Normalizar comparación
        urls = set()
        for item in existing:
            if isinstance(item, dict):
                u = item.get("url") or item.get("callback_url") or ""
                if u:
                    urls.add(u.rstrip("/"))

        if webhook_url.rstrip("/") in urls:
            self.stdout.write(self.style.SUCCESS(f"Ya existe webhook para: {webhook_url}"))
            return

        events = [e.strip() for e in options["events"].split(",") if e.strip()]
        payload = {
            "url": webhook_url,
            "events": events,
        }

        self.stdout.write(self.style.NOTICE(f"Creando webhook → {webhook_url} events={events}"))
        create = requests.post(
            f"{MP_API}/v1/webhooks",
            headers=headers,
            json=payload,
            timeout=30,
        )

        if create.status_code in (200, 201):
            self.stdout.write(self.style.SUCCESS("Webhook creado:"))
            self.stdout.write(json.dumps(create.json(), indent=2, ensure_ascii=False))
            secret = create.json().get("secret") or create.json().get("webhook_secret")
            if secret:
                self.stdout.write(
                    self.style.WARNING(
                        f"Guarda este secreto en MERCADOPAGO_WEBHOOK_SECRET:\n{secret}"
                    )
                )
            return

        # Fallback: documentación de notificaciones por aplicación
        self.stdout.write(
            self.style.ERROR(
                f"No se pudo crear vía API ({create.status_code}): {create.text[:500]}\n\n"
                "Alternativa (panel MP):\n"
                "  1. https://www.mercadopago.com.co/developers/panel/app\n"
                "  2. Tu aplicación → Webhooks\n"
                f"  3. URL: {webhook_url}\n"
                f"  4. Eventos: {', '.join(events)}\n"
                "  5. Copia el 'Secret key' a MERCADOPAGO_WEBHOOK_SECRET\n\n"
                "cURL de referencia:\n"
                f"curl -X POST '{MP_API}/v1/webhooks' \\\n"
                f"  -H 'Authorization: Bearer $MERCADOPAGO_ACCESS_TOKEN' \\\n"
                "  -H 'Content-Type: application/json' \\\n"
                f"  -d '{json.dumps(payload)}'"
            )
        )
        raise CommandError("Falló la creación del webhook")
