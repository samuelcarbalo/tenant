# Guía de despliegue a producción — CordobaTech (multi-tenant)

Guía global para llevar a producción **el backend** (Django + DRF + Channels/WebSockets) y **el frontend** (React + Vite, PWA), de la forma más económica y eficiente posible.

---

## 1. Arquitectura

| Componente | Tecnología | Necesita |
|---|---|---|
| Frontend | React + Vite (PWA, estático) | Solo servir archivos estáticos + CDN |
| Backend | Django + DRF + Channels (ASGI) | Proceso Python persistente, WebSockets |
| Base de datos | PostgreSQL | Servidor Postgres |
| Cache / colas / WebSockets | Redis | Servidor Redis |
| Pagos | Mercado Pago (Checkout Pro) | Webhook con URL pública HTTPS |
| Archivos media (uploads) | Disco / almacenamiento | Volumen persistente o S3/R2 |

> Importante: el backend usa **WebSockets (Channels)**, por lo que **no** sirve un hosting puramente "serverless" sin soporte de conexiones persistentes. Necesitas un proceso ASGI corriendo (Daphne/Uvicorn) y Redis.

---

## 2. Checklist previo (bloqueantes)

- [ ] `SECRET_KEY` nueva y secreta (no la de desarrollo).
- [ ] `DEBUG=False` (ya forzado en `production.py`).
- [ ] `ALLOWED_HOSTS` con tu dominio real.
- [ ] `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` con el dominio del frontend.
- [ ] PostgreSQL creado y accesible.
- [ ] Redis accesible.
- [ ] Credenciales de **Mercado Pago de PRODUCCIÓN** (las actuales son de prueba).
- [ ] Webhook de MP apuntando a `https://TU_BACKEND/api/v1/payments/webhook/`.
- [ ] **Validación de firma del webhook** de MP (hoy no valida `x-signature` — ver §7).
- [ ] `collectstatic` ejecutado y estáticos servidos (WhiteNoise ya configurado).
- [ ] HTTPS activo (certificado TLS).
- [ ] Estrategia de backups de la BD.

---

## 3. Variables de entorno

### Backend (`tenant/.env` en el servidor)

```env
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=<genera-una-clave-larga-y-aleatoria>

# Hosts / dominios
ALLOWED_HOSTS=api.tudominio.com
CORS_ALLOWED_ORIGINS=https://tudominio.com
CSRF_TRUSTED_ORIGINS=https://tudominio.com

# PostgreSQL
POSTGRES_DB=cordobatech
POSTGRES_USER=cordobatech
POSTGRES_PASSWORD=<password-seguro>
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432

# Redis
REDIS_URL=redis://127.0.0.1:6379/1

# URLs públicas
FRONTEND_URL=https://tudominio.com
BACKEND_URL=https://api.tudominio.com

# Mercado Pago (PRODUCCIÓN)
MERCADOPAGO_PUBLIC_KEY=APP_USR-...
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...
MERCADOPAGO_WEBHOOK_URL=https://api.tudominio.com/api/v1/payments/webhook/

# Email (SMTP real)
EMAIL_HOST=smtp.tuservidor.com
EMAIL_PORT=587
EMAIL_HOST_USER=no-reply@tudominio.com
EMAIL_HOST_PASSWORD=<password>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=no-reply@tudominio.com

# Seguridad
SECURE_SSL_REDIRECT=True

# Opcional: monitoreo de errores
# SENTRY_DSN=https://...@sentry.io/...
```

Genera una `SECRET_KEY` con:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Frontend (`.env` de build)

```env
VITE_API_URL=https://api.tudominio.com/api/v1
VITE_TENANT_SLUG=conectando-empleo
VITE_MERCADOPAGO_PUBLIC_KEY=APP_USR-...   # public key de PRODUCCIÓN
VITE_IMGBB_API_KEY=<tu-key>
```

---

## 4. Despliegue del backend (pasos)

```bash
# 1. Dependencias
pip install -r requirements.txt

# 2. Migraciones
python manage.py migrate

# 3. Estáticos (WhiteNoise los sirve comprimidos)
python manage.py collectstatic --noinput

# 4. Crear superusuario (una vez)
python manage.py createsuperuser

# 5. Servir con ASGI (soporta WebSockets)
daphne -b 0.0.0.0 -p 8000 config.asgi:application
# o con gunicorn + uvicorn workers:
# gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 -w 3
```

Delante conviene un **nginx** como reverse proxy que:
- Termina TLS (HTTPS).
- Envía `X-Forwarded-Proto: https` (ya contemplado en `SECURE_PROXY_SSL_HEADER`).
- Hace proxy de `/ws/` con `Upgrade`/`Connection` para WebSockets.

---

## 5. Despliegue del frontend (pasos)

```bash
npm ci
npm run build      # genera dist/ (con service worker PWA)
```

Sube el contenido de `dist/` a un hosting de estáticos + CDN. Configura el fallback SPA (todas las rutas → `index.html`).

---

## 6. Webhook de Mercado Pago

1. En el panel de MP → tu aplicación → **Webhooks/Notificaciones**, registra:
   `https://api.tudominio.com/api/v1/payments/webhook/`
2. Suscríbete al evento **payment**.
3. En local (testing) usa `ngrok http 8000` y pon esa URL en `MERCADOPAGO_WEBHOOK_URL`, o acredita manual con:
   ```bash
   python manage.py apply_payment <payment_id>
   ```

---

## 7. Seguridad — pendiente importante

El endpoint del webhook **hoy no valida la firma** `x-signature` de Mercado Pago. En producción cualquiera podría llamarlo. Antes de ir a producción con dinero real:

- Validar el header `x-signature` + `x-request-id` con tu **clave secreta de webhook** (MP la entrega en el panel).
- Verificar que el `payment_id` consultado a la API de MP realmente esté `approved` antes de acreditar (esto ya lo hace `apply_approved_payment` vía `get_payment`, pero conviene reforzar la firma).

Otras recomendaciones ya cubiertas por `production.py`: HSTS, cookies seguras, `SECURE_SSL_REDIRECT`, `X_FRAME_OPTIONS=DENY`, throttling sobre Redis.

---

## 8. Dónde alojar (económico y eficiente)

### 8.1. Frontend (estático + CDN) — prácticamente gratis

| Opción | Costo | Notas |
|---|---|---|
| **Cloudflare Pages** | Gratis | CDN global, builds ilimitados, dominio propio. **Recomendado.** |
| Vercel (Hobby) | Gratis | Muy fácil con Vite; límite de uso comercial en plan free. |
| Netlify | Gratis | Similar; 100 GB/mes. |

> El frontend es estático, no necesita servidor. Cualquiera de estos con dominio propio + HTTPS gratis.

### 8.2. Backend + Postgres + Redis

Como necesitas **WebSockets + Redis + Postgres**, hay dos caminos:

#### Opción A — VPS único (la más económica y con más control) ✅ Recomendada
Un solo servidor con Docker corriendo Django (Daphne) + nginx + Postgres + Redis.

| Proveedor | Plan | Costo aprox. |
|---|---|---|
| **Hetzner Cloud** CX22 | 2 vCPU / 4 GB RAM | **~€4–5/mes** (lo más barato/potente) |
| Contabo VPS | 4 vCPU / 8 GB | ~€6/mes |
| DigitalOcean Droplet | 1 vCPU / 2 GB | ~$12/mes |
| Oracle Cloud Free Tier | ARM 4 vCPU / 24 GB | Gratis (si hay disponibilidad) |

Ventaja: todo en una máquina, sin costos por servicio separado. Desventaja: tú administras backups y actualizaciones.

**Estimado total (Opción A):** ~€5/mes backend + frontend gratis = **~€5/mes**.

#### Opción B — Plataforma administrada (menos mantenimiento)
Backend en PaaS + BD/Redis administrados (con generosos free tiers).

| Servicio | Uso | Costo |
|---|---|---|
| **Render** / **Railway** / **Fly.io** | Web service ASGI (soportan WebSockets) | desde ~$5–7/mes |
| **Neon** o **Supabase** | Postgres administrado | Free tier suficiente para empezar |
| **Upstash** | Redis administrado | Free tier (10k comandos/día) |

**Estimado total (Opción B):** ~$5–7/mes backend + Postgres/Redis gratis + frontend gratis.

> Recomendación: si te sientes cómodo con Linux/Docker, **Opción A (Hetzner)** es la más barata y eficiente. Si prefieres cero administración, **Opción B (Render + Neon + Upstash + Cloudflare Pages)**.

### 8.3. Archivos subidos (media)
- Si usas VPS: guarda en un volumen del servidor (simple) o en **Cloudflare R2** (S3-compatible, egress gratis, muy barato).
- En PaaS el disco suele ser efímero → usa **Cloudflare R2** o **AWS S3** para uploads.

---

## 9. Despliegue recomendado paso a paso (Opción A: Hetzner + Docker)

1. Crea un VPS Hetzner CX22 (Ubuntu 22.04) y apunta tus dominios (`tudominio.com`, `api.tudominio.com`) por DNS.
2. Instala Docker + Docker Compose.
3. Levanta contenedores: `web` (Daphne), `db` (Postgres), `redis`, `nginx` (reverse proxy + TLS con Let's Encrypt/Certbot o Caddy).
4. Copia el `.env` de producción al servidor.
5. `docker compose run web python manage.py migrate && collectstatic`.
6. Publica el frontend en Cloudflare Pages apuntando `VITE_API_URL` a `https://api.tudominio.com/api/v1`.
7. Configura el webhook de MP y prueba un pago real de bajo monto.
8. Activa backups automáticos de Postgres (snapshot Hetzner o `pg_dump` a R2 vía cron).

---

## 10. Post-despliegue

- [ ] Probar registro/login, publicar empleo/torneo, y un pago real de prueba.
- [ ] Verificar WebSockets (chat/notificaciones) en HTTPS.
- [ ] Confirmar que los créditos se acreditan por webhook automáticamente.
- [ ] Monitoreo: activar Sentry (`SENTRY_DSN`) para capturar errores.
- [ ] Programar backups y probar una restauración.
- [ ] Revisar logs (`docker compose logs -f web`).

---

### Resumen ejecutivo
- **Frontend:** Cloudflare Pages (gratis).
- **Backend más barato:** VPS Hetzner ~€5/mes con Docker (Django+Redis+Postgres+nginx).
- **Backend sin mantenimiento:** Render/Railway + Neon (Postgres) + Upstash (Redis), casi todo en free tier.
- **Antes de cobrar en serio:** cambiar a credenciales MP de producción y **validar la firma del webhook**.
