# Guía de diseño — Módulo Eventos

Documento de referencia para implementar la sección **Eventos** en CordobaTech.  
Estado actual: placeholder en frontend (`/events` → "Próximamente") y tipo `Event` en `src/types/index.ts` sin backend.

---

## Contexto en la plataforma hoy

| Módulo | Qué publica | Créditos | Diferencia clave |
|--------|-------------|----------|------------------|
| **Empleos** | Vacantes laborales | 5 | Oferta de trabajo |
| **Bienes raíces** | Propiedades | 5 | Venta/alquiler |
| **Deportes** | Torneos/ligas | 50 | Competición estructurada (equipos, partidos, tabla) |
| **Banners** (`sports.AdvertisementBanner`) | Publicidad visual | — | Solo imagen + link, sin ficha de evento |
| **Eventos** (pendiente) | ? | ? | **Por definir** |

El riesgo principal es **solaparse con deportes** (partido vs evento deportivo) o **con banners** (flyer vs evento con fecha/lugar).

---

## Recomendación principal: app `events` tipo “clasificado con calendario”

Tratar los eventos como **publicaciones de agenda local** — ferias, conciertos, lanzamientos, networking, activaciones de marca — no como torneos.

### Por qué encaja mejor

1. **Mismo patrón** que `jobs` y `real_estate`: crear app, ViewSet, 5 créditos, expira a 30 días, moderación, reportes.
2. **Monetización ya resuelta** con la cartera de créditos y Mercado Pago.
3. **SEO**: ruta `/eventos` + Schema.org `Event` (Google puede mostrar fecha/lugar en resultados).
4. **Separación clara de deportes**: torneo = `/deportes`; evento social/publicitario = `/eventos`.

### Modelo sugerido (`EventListing`)

```
title, description, slug
event_category: feria | concierto | negocios | cultural | gastronomico | otro
start_datetime, end_datetime
location, address, is_online, online_url
cover_image (URL o FileField)
organizer_name, contact_phone, contact_email, external_link
price_info (texto libre: "Gratis", "Desde $20.000", etc.)
is_featured (bool) — opcional, pago extra
organization, posted_by
posted_at, expires_at, is_active
moderation_status (reutilizar patrón actual)
views_count, impressions
```

**Costo sugerido:** **5 créditos** (igual que empleo/inmueble) o **8 créditos** si incluye imagen destacada en home.

---

## Tres formas de introducirlo (comparativa)

### Opción 1 — Listado simple (MVP) ⭐ Recomendada para empezar

- Feed en `/eventos` con filtros: fecha, categoría, ciudad.
- Detalle con mapa/link, botón compartir, **Reportar**.
- Publicar solo `manager`/`admin` con créditos (como empleos).
- Sin inscripciones ni tickets en v1.

**Pros:** 1–2 sprints, reutiliza casi todo el stack.  
**Contras:** no diferencia “evento premium” sin un upsell.

---

### Opción 2 — Evento + espacio publicitario (híbrido)

Combinar **ficha de evento** (app `events`) con **slots de banner** existentes (`AdvertisementBanner`):

| Producto | Qué obtiene el anunciante |
|----------|---------------------------|
| Publicación básica | Ficha en `/eventos` (5 créditos) |
| Destacado en home | Banner `home_hero` + ficha (5 + X créditos o paquete “Evento Pro”) |
| Destacado en listado | Badge “Patrocinado” arriba del feed |

**Pros:** ingresos extra; aprovechas banners ya construidos.  
**Contras:** dos sistemas que coordinar en UI (“¿solo ficha o ficha + banner?”).

---

### Opción 3 — Marketplace de activaciones B2B

Orientado a **empresas que promocionan** en la región:

- Paquetes: “Evento + email a usuarios de la org” (futuro), “Evento + notificación push”.
- Métricas: vistas, clicks en `external_link`.
- Panel para el organizer: “Mis eventos publicados”.

**Pros:** alineado con “evento publicitario” que mencionas.  
**Contras:** más producto y analytics; mejor como fase 2.

---

## Qué NO mezclar

| Evitar | Motivo |
|--------|--------|
| Usar `Tournament` para eventos sociales | Modelo pensado para equipos/partidos/standings |
| Solo `AdvertisementBanner` sin ficha | No hay calendario, búsqueda por fecha ni SEO Event |
| Duplicar “eventos deportivos” | Partidos ya viven en `Match`; torneos en `Tournament` |

**Regla de producto:** si tiene **tabla de posiciones o plantilla**, es deportes. Si tiene **fecha, lugar y flyer**, es eventos.

---

## Integraciones a reutilizar (sin reinventar)

| Sistema | Uso en eventos |
|---------|----------------|
| `User.credits` + `payments` | Cobrar publicación |
| `moderation.ReportePublicacion` | Añadir `content_type: "event"` |
| `notifications` | “Tu evento expira en 3 días” |
| `messaging` | “Contactar organizador” (opcional) |
| SEO frontend | `/eventos`, JSON-LD `Event`, sitemap priority 0.9 |
| PWA shortcuts | Quinto shortcut “Eventos” → `/eventos` |

---

## UX frontend sugerida

1. **Home:** tarjeta Eventos activa (hoy dice “Próximamente”).
2. **Listado:** vista calendario + vista lista; filtros por mes/categoría.
3. **Detalle:** hero con imagen, fechas, mapa, CTA “Más información” (link externo o WhatsApp).
4. **Publicar:** `/eventos/publicar` — mismo flujo que empleos (créditos + formulario).
5. **Dashboard manager:** “Mis eventos” con renovar (30 días) como jobs/real-estate.

---

## Roadmap sugerido

### Fase 1 — MVP (2 semanas)
- App `events` backend + migraciones
- CRUD + descuento 5 créditos
- Frontend listado, detalle, crear
- Ruta SEO `/eventos`, moderación, reportes

### Fase 2 — Monetización extra
- Paquete créditos “Evento destacado”
- Vincular con `AdvertisementBanner` position `events_feed_top`

### Fase 3 — Engagement
- Recordatorios por notificación
- “Me interesa” / contador de interesados (sin ticket aún)
- Export iCal / “Añadir al calendario”

---

## Decisión rápida

Si tu prioridad es **“alguien publica un evento publicitario local”**, la mejor entrada es:

> **App `events` + 5 créditos + ficha con fecha/lugar/imagen**,  
> y en una segunda iteración **vender visibilidad extra** con los banners que ya tienes en deportes extendidos a `position: "events_hero"`.

¿Quieres que en el siguiente paso implemente el MVP de la Fase 1 (backend + frontend)?
