#!/usr/bin/env bash
# Consultar / crear webhook de Mercado Pago (cURL)
# Uso:
#   export MP_ACCESS_TOKEN="APP_USR-..."
#   export WEBHOOK_URL="https://missingdigitalback.onrender.com/api/v1/payments/webhook/"
#   bash scripts/mp_webhook_setup.sh

set -euo pipefail

MP_ACCESS_TOKEN="${MP_ACCESS_TOKEN:-${MERCADOPAGO_ACCESS_TOKEN:-}}"
WEBHOOK_URL="${WEBHOOK_URL:-https://missingdigitalback.onrender.com/api/v1/payments/webhook/}"
API="https://api.mercadopago.com"

if [[ -z "${MP_ACCESS_TOKEN}" ]]; then
  echo "Define MP_ACCESS_TOKEN o MERCADOPAGO_ACCESS_TOKEN"
  exit 1
fi

echo "==> Listando webhooks…"
curl -sS -X GET "${API}/v1/webhooks" \
  -H "Authorization: Bearer ${MP_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" | python -m json.tool || true

echo ""
echo "==> Creando webhook si el panel/API lo permite…"
curl -sS -X POST "${API}/v1/webhooks" \
  -H "Authorization: Bearer ${MP_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"${WEBHOOK_URL}\",\"events\":[\"payment\",\"merchant_order\"]}" \
  | python -m json.tool || true

echo ""
echo "Si la API no está disponible para tu cuenta, configura el webhook en:"
echo "  https://www.mercadopago.com.co/developers/panel/app → Webhooks"
echo "URL: ${WEBHOOK_URL}"
echo "Luego guarda el Secret en MERCADOPAGO_WEBHOOK_SECRET"
