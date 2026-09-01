# CordobaTech — Backend Multi-Tenant

API REST Django 4.2 + DRF + JWT + Django Channels para la plataforma CordobaTech: empleos, deportes, bienes raíces, mensajería, notificaciones, pagos (Mercado Pago) y moderación de contenido.

## Stack

- Django 4.2 · Django REST Framework · SimpleJWT
- Django Channels + Daphne (WebSockets)
- Multi-tenant por organización (`X-Tenant` header)
- SQLite (dev) · PostgreSQL (prod)
- Mercado Pago Checkout Pro (`mercadopago` SDK)

## Inicio rápido

```bash
# Entorno virtual (Windows)
D:
cd D:\app_multi_tenant
venv\Scripts\activate
cd tenant
python manage.py runserver --settings=config.settings.development
python manage.py runserver --settings=config.settings.production


pip install -r requirements.txt

# Migraciones
python manage.py migrate --settings=config.settings.development
# En producción (Render) solo aplicar, nunca makemigrations:
# python manage.py migrate --settings=config.settings.production

# Servidor HTTP
python manage.py runserver --settings=config.settings.development
python manage.py runserver --settings=config.settings.production

# WebSockets (mensajería) — terminal aparte
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

| URL | Descripción |
|-----|-------------|
| API | http://127.0.0.1:8000/api/v1/ |
| Admin | http://127.0.0.1:8000/admin/ |

## Variables de entorno (`.env`)

```env
SECRET_KEY=tu-clave-secreta-larga-min-32-chars
DEBUG=True
DJANGO_SETTINGS_MODULE=config.settings.development

DB_NAME=multitenant_db
DB_USER=postgres
DB_PASSWORD=postgres
REDIS_URL=redis://127.0.0.1:6379/1

# Mercado Pago — Sandbox / Producción
MERCADOPAGO_PUBLIC_KEY=APP_USR-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MERCADOPAGO_ACCESS_TOKEN=APP_USR-xxxxxxxx-xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx-xxxxxxxxxx
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000
MERCADOPAGO_WEBHOOK_URL=https://tu-dominio-o-ngrok/api/v1/payments/webhook/

# Comisiones (referencia fiscal DIAN)
MP_COMMISSION_RATE=0.0329
MP_IVA_RATE=0.19
MP_WITHDRAWAL_ALERT_DAYS=150
MP_WITHDRAWAL_MAX_DAYS=180
```

> En **localhost**, `auto_return` de MP solo se activa si `FRONTEND_URL` es `https://`. El webhook solo se envía a MP si la URL es HTTPS (usar ngrok en desarrollo).

---

## Apps del proyecto

| App | Descripción |
|-----|-------------|
| `authentication` | Usuarios, JWT, login multi-tenant, campo `credits` |
| `organizations` | Tenants / organizaciones |
| `profiles` | Perfiles de usuario |
| `jobs` | Ofertas de empleo y postulaciones |
| `sports` | Torneos, equipos, jugadores, partidos |
| `real_estate` | Propiedades inmobiliarias |
| `messaging` | Chat REST + WebSocket (Channels) |
| `notifications` | Notificaciones in-app |
| `payments` | Mercado Pago, órdenes, facturación |
| `moderation` | Reportes de publicaciones |

---

## Sistema de créditos (cartera interna)

### Costos de consumo

| Acción | Créditos | Equivalente |
|--------|----------|-------------|
| Publicar empleo | 5 | $5.000 COP |
| Publicar inmueble | 5 | $5.000 COP |
| Crear torneo de fútbol | 50 | $50.000 COP |

El campo `User.credits` (entero, default 0) se descuenta de forma atómica en `perform_create` de jobs, real_estate y sports.

### Paquetes de compra (Mercado Pago)

Definidos en `payments/packages.py`:

| ID | Créditos | Precio COP |
|----|----------|------------|
| `basico` | 20 | 20.000 |
| `bronce` | 30 | 28.000 |
| `plata` | 50 | 45.000 |
| `oro` | 100 | 80.000 |

### Endpoints de pagos (`/api/v1/payments/`)

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/packages/` | Público | Lista de paquetes |
| GET | `/config/` | Público | Public Key para el frontend |
| POST | `/create-preference/` | Sí | Crea preferencia Checkout Pro → `preference_id` |
| GET | `/my-orders/` | Sí | Historial de órdenes del usuario |
| GET | `/billing/` | Admin | Transacciones de facturación |
| POST/GET | `/webhook/` | Público | Webhook MP — acredita créditos si `approved` |

### Modelos (`payments/`)

- **`PaymentOrder`** — orden pendiente/aprobada, `mp_preference_id`, `mp_payment_id`
- **`TransaccionFacturacion`** — `monto_total`, `comision_mercado_pago` (3.29%), `iva_comision` (19%), `monto_neto_recibido`
- **`WithdrawalAlert`** — alerta administrativa para retiro ACH antes de 180 días

### Servicios

```
payments/services/
├── mercadopago_service.py   # Crear preferencia, consultar pago
├── payment_processor.py     # Acreditación idempotente de créditos
├── billing.py               # Cálculo comisiones e IVA
└── withdrawal_alert.py      # Alerta de retiro de fondos
```

### Comando de alerta de retiro

```bash
python manage.py check_mp_withdrawal --settings=config.settings.development
```

Ejecutar vía cron diario en producción.

---

## Moderación de contenido

### Modelo `ReportePublicacion` (`moderation/`)

- Motivos: `fraude`, `contenido_inapropiado`, `discriminacion`
- GenericForeignKey hacia empleos, inmuebles o torneos
- Un reporte por usuario por publicación (`unique_together`)

### Auto-moderación

Con **≥ 3 reportes** la publicación pasa a `moderation_status = pendiente_revision` y se oculta del feed (`is_active = False` en empleos/inmuebles).

Campo añadido en: `JobOffer`, `RealEstateOffer`, `Tournament`.

### Endpoint

```
POST /api/v1/moderation/reports/
{
  "content_type": "job" | "real_estate" | "tournament",
  "object_id": "uuid",
  "reason": "fraude" | "contenido_inapropiado" | "discriminacion",
  "description": "opcional"
}
```

---

## Mensajería (`messaging/`)

- Conversaciones polimórficas (postulación de empleo, inmueble)
- Chat automático al postularse a un empleo (signal en `JobApplication`)
- REST: `/api/v1/messaging/conversations/`
- WebSocket: `ws/messaging/conversations/{id}/?token={jwt}`

Documentación detallada: `MESSAGING_ARCHITECTURE.md`

---

## Notificaciones (`notifications/`)

- Tipos: `chat_message`, `job_status_change`
- Auto-disparo al recibir mensajes o cambiar estado de postulación
- Endpoints: list, mark-read, mark-all-read, unread-count

---

## API principal (prefijo `/api/v1/`)

| Prefijo | Recursos |
|---------|----------|
| `/auth/` | login, register, refresh, me |
| `/profiles/` | perfiles |
| `/organizations/` | tenants |
| `/jobs/offers/` · `/jobs/applications/` | empleos |
| `/sports/tournaments/` · `/teams/` · `/matches/` | deportes |
| `/real-estate/offers/` | inmuebles |
| `/messaging/` | chat |
| `/notifications/` | notificaciones |
| `/payments/` | créditos y MP |
| `/moderation/` | reportes |

Documento de diseño del módulo **Eventos** (pendiente): [`docs/EVENTOS_DISENO.md`](docs/EVENTOS_DISENO.md)

---

## Pruebas

```bash
# Suite completa (auth + integración API)
python manage.py test --settings=config.settings.development -v 2

# Solo integración (pagos, moderación, jobs, etc.)
python manage.py test core.tests_api_integration --settings=config.settings.development -v 2

# Smoke test contra servidor en vivo (requiere runserver en :8000)
python scripts/smoke_test_api.py
```

**Cobertura de tests de integración** (`core/tests_api_integration.py`):

- Auth: login, `/auth/me/`
- Payments: paquetes, config MP, preferencia (mock), webhook, facturación
- Moderation: reporte, auto-ocultar con 3 reportes
- Jobs: listado, descuento de créditos al publicar
- Real estate, sports, messaging, notifications, profiles

---

## Comandos útiles

```bash
# Crear migraciones (solo desarrollo — genera 000X_*.py)
python manage.py makemigrations --settings=config.settings.development
python manage.py migrate --settings=config.settings.development

# Producción / Render: aplicar las migraciones ya commiteadas (nunca makemigrations)
python manage.py migrate --settings=config.settings.production
python manage.py collectstatic --noinput --settings=config.settings.production

# Superusuario
python manage.py createsuperuser --settings=config.settings.development

# Shell
python manage.py shell --settings=config.settings.development

# Ver migraciones
python manage.py showmigrations --settings=config.settings.development
```

### Git (referencia)

```bash
D:
cd D:\app_multi_tenant\tenant
git add .
git commit -m "api rest optimized"
git push origin test
```

### Limpiar caché Python

```bash
del /s /q __pycache__
del /s /q *.pyc
```

---

## Estructura de carpetas relevante

```
tenant/
├── config/
│   ├── settings/base.py      # INSTALLED_APPS, MP, JWT, Channels
│   └── urls.py               # /api/v1/* includes
├── payments/
│   ├── packages.py           # Paquetes y costos
│   ├── models.py             # PaymentOrder, TransaccionFacturacion
│   ├── views.py              # Preferencia, webhook
│   └── services/             # MP, billing, processor
├── moderation/
│   ├── models.py             # ReportePublicacion
│   └── services.py           # Auto-ocultar publicaciones
├── messaging/                # Chat + WebSocket consumers
├── notifications/
├── jobs/ · sports/ · real_estate/
├── core/tests_api_integration.py
├── docs/EVENTOS_DISENO.md      # Guía módulo Eventos (pendiente)
└── scripts/smoke_test_api.py
```

---

## WebSockets y producción

- **Dev:** `InMemoryChannelLayer` (settings development)
- **Prod:** Redis (`channels-redis`) — configurar `REDIS_URL`
- Servir ASGI con **Daphne** o similar para HTTP + WebSockets en el mismo puerto

---

## Notas de seguridad

- No commitear `.env` con tokens de Mercado Pago.
- Usar `SECRET_KEY` de al menos 32 caracteres en producción.
- Configurar `MERCADOPAGO_WEBHOOK_URL` con HTTPS y validar origen en producción.
- Rotar credenciales sandbox/producción por separado en el [Panel de Desarrolladores MP](https://www.mercadopago.com.co/developers).
