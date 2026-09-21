# Mercado Pago — Webhooks

## URL del endpoint (backend Django)

Usar el backend (Render), **no** el frontend de Hostinger:

```
https://missingdigitalback.onrender.com/api/v1/payments/webhook/
```

Alias equivalente:

```
https://missingdigitalback.onrender.com/api/webhooks/mercadopago/
```

`notification_url` en preferencias Checkout Pro y el webhook del panel MP deben apuntar a una de estas URLs (HTTPS).

## 1) Listar / crear webhook

### Management command

```bash
cd tenant
python manage.py sync_mp_webhooks --list
python manage.py sync_mp_webhooks --ensure \
  --url https://missingdigitalback.onrender.com/api/v1/payments/webhook/
```

### cURL

```bash
export MP_ACCESS_TOKEN="APP_USR-..."
export WEBHOOK_URL="https://missingdigitalback.onrender.com/api/v1/payments/webhook/"

# Listar
curl -sS -X GET "https://api.mercadopago.com/v1/webhooks" \
  -H "Authorization: Bearer $MP_ACCESS_TOKEN"

# Crear (payment + merchant_order)
curl -sS -X POST "https://api.mercadopago.com/v1/webhooks" \
  -H "Authorization: Bearer $MP_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"$WEBHOOK_URL\",\"events\":[\"payment\",\"merchant_order\"]}"
```

Script: `tenant/scripts/mp_webhook_setup.sh`

Si la API REST de webhooks no está habilitada en tu cuenta, créalo en el panel:

1. [Developers Panel](https://www.mercadopago.com.co/developers/panel/app)
2. Tu aplicación → **Webhooks**
3. URL + eventos `payment`, `merchant_order`
4. Copia el **Secret key** → `MERCADOPAGO_WEBHOOK_SECRET`

## 2) Variables de entorno

```env
MERCADOPAGO_ACCESS_TOKEN=...
MERCADOPAGO_WEBHOOK_URL=https://missingdigitalback.onrender.com/api/v1/payments/webhook/
MERCADOPAGO_WEBHOOK_SECRET=...   # firma x-signature
```

## 3) Flujo hacia la PWA

1. MP envía POST al webhook con `x-signature` / `x-request-id`
2. Backend valida firma, guarda `MercadoPagoWebhookEvent` y responde **200 `received`** de inmediato
3. El pago se consulta y acredita en segundo plano (sandbox o live según `is_production`)
4. Si `approved` → acredita créditos / cumple pedido de tienda + `Notification` (`payment_success`)
5. La PWA consulta `GET /api/v1/payments/status/` y `GET /api/v1/notifications/`
6. El usuario marca leídas con `POST /notifications/{id}/mark-read/`

No hay WebSocket de notificaciones: el panel usa REST + polling.
