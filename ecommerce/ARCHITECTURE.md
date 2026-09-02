# E-commerce CAPISJ DIGITAL

## Reutilización
- **Pagos**: `MercadoPagoService.create_preference_from_items` + webhook en `payments.views` (resuelve `PaymentOrder` o `ShopOrder`).
- **Auth / org**: JWT + `X-Tenant` (`OrganizationMiddleware`).
- **UI**: `MainLayout`, `MercadoPagoCheckout`, React Query, Zustand cart.
- **Créditos**: independientes (publicar contenido). La tienda cobra COP, no créditos.

## Modelos
- `Category`, `Product`, `Discount`, `ShopOrder`, `ShopOrderItem`
- Índices por org/slug/precio; `select_related`/`prefetch_related` en listados/pedidos.
- Cache Redis/LocMem: categorías (5 min) y detalle producto (2 min).

## API (`/api/v1/ecommerce/`)
| Método | Ruta | Auth |
|--------|------|------|
| GET | `/categories/` | pública lectura |
| CRUD | `/categories/` | manager |
| GET | `/products/?category=&search=&min_price=&max_price=` | pública |
| CRUD | `/products/{slug}/` | manager write |
| CRUD | `/discounts/` | manager |
| GET | `/orders/` | buyer |
| POST | `/orders/checkout/` | buyer → preferencia MP |

## Frontend
- `/tienda`, `/tienda/:slug`, `/tienda/carrito`, `/tienda/checkout`, `/tienda/resultado`
- Carrito local (`cartStore`) → checkout autenticado → Wallet MP.

## Deploy
```bash
python manage.py migrate ecommerce
```
