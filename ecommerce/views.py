import logging

from django.core.cache import cache
from django.db import DatabaseError
from django.db.utils import OperationalError, ProgrammingError
from django.http import Http404
from django.db.models import Prefetch
from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response

from ecommerce.models import Category, Discount, Product, ShopOrder, ShopOrderItem
from ecommerce.serializers import (
    CategorySerializer,
    CheckoutSerializer,
    DiscountSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductWriteSerializer,
    ShopOrderSerializer,
)
from ecommerce.services import (
    categories_cache_key,
    create_shop_order,
    invalidate_catalog_cache,
    product_detail_cache_key,
)
from core.permissions import resolve_request_organization, user_can_manage_content
from jobs.permissions import IsManagerOfOrganization, IsManagerOrReadOnly
from payments.services.mercadopago_service import MercadoPagoService

logger = logging.getLogger(__name__)

_MISSING_TABLE_MSG = "Las tablas de e-commerce no existen o no se han migrado."


def _catalog_error(exc):
    """
    Error controlado JSON 500 (no tumba el worker).
    DatabaseError/ProgrammingError → mensaje explícito de migraciones.
    """
    logger.exception("Ecommerce catalog failed: %s", exc)
    detail = str(exc) or exc.__class__.__name__
    is_db = isinstance(exc, (DatabaseError, ProgrammingError, OperationalError))
    payload = {
        "success": False,
        "error": _MISSING_TABLE_MSG if is_db else detail,
        "details": detail,
        "count": 0,
        "results": [],
        "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _ecommerce_table_status():
    from django.db import connection

    required = (
        "ecommerce_categories",
        "ecommerce_products",
        "ecommerce_discounts",
        "ecommerce_orders",
        "ecommerce_order_items",
    )
    try:
        existing = set(connection.introspection.table_names())
        missing = [t for t in required if t not in existing]
        return {
            "ok": not missing,
            "missing_tables": missing,
            "ecommerce_in_installed_apps": True,
        }
    except Exception as exc:
        logger.exception("ecommerce health introspection failed")
        return {"ok": False, "missing_tables": list(required), "introspection_error": str(exc)}


class PublicReadManagerWrite(IsManagerOrReadOnly):
    """Lectura pública; escritura para managers o admins/superusuarios de plataforma."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return user_can_manage_content(request.user)


def _request_org(request):
    org = getattr(request, "current_organization", None)
    if org:
        return org
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return getattr(user, "organization", None)
    return None


class ProductFilter(filters.FilterSet):
    category = filters.CharFilter(field_name="category__slug")
    min_price = filters.NumberFilter(field_name="price_cop", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price_cop", lookup_expr="lte")
    featured = filters.BooleanFilter(field_name="is_featured")
    in_stock = filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = Product
        fields = ["category", "min_price", "max_price", "featured"]

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock__gt=0)
        return queryset


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [PublicReadManagerWrite, IsManagerOfOrganization]
    lookup_field = "slug"
    search_fields = ["name", "description"]
    ordering_fields = ["sort_order", "name", "created_at"]
    ordering = ["sort_order", "name"]

    def get_queryset(self):
        try:
            qs = Category.objects.select_related("organization")
            org = _request_org(self.request)
            if org:
                qs = qs.filter(organization=org)
            if self.action in ("list", "retrieve"):
                qs = qs.filter(is_active=True)
            return qs
        except Exception as e:
            logger.error("CategoryViewSet.get_queryset failed: %s", e, exc_info=True)
            raise

    @action(detail=False, methods=["get"], url_path="health", permission_classes=[AllowAny])
    def health(self, request):
        """Diagnóstico de tablas ecommerce (público)."""
        payload = _ecommerce_table_status()
        code = status.HTTP_200_OK if payload.get("ok") else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(payload, status=code)

    def list(self, request, *args, **kwargs):
        try:
            org = _request_org(request)
            if org and request.method == "GET":
                key = categories_cache_key(str(org.id))
                try:
                    cached = cache.get(key)
                except Exception:
                    logger.exception("Cache get falló para categorías")
                    cached = None
                if cached is not None:
                    return Response(cached)
                response = super().list(request, *args, **kwargs)
                try:
                    if response.status_code == 200 and isinstance(response.data, dict) and "results" in response.data:
                        cache.set(key, response.data, 300)
                    elif response.status_code == 200 and isinstance(response.data, list):
                        cache.set(key, response.data, 300)
                except Exception:
                    logger.exception("Cache set falló para categorías")
                return response
            return super().list(request, *args, **kwargs)
        except Http404:
            raise
        except APIException:
            raise
        except (DatabaseError, ProgrammingError, OperationalError) as e:
            logger.error("CategoryViewSet.list DB error: %s", e, exc_info=True)
            return _catalog_error(e)
        except Exception as e:
            logger.error("CategoryViewSet.list failed: %s", e, exc_info=True)
            return _catalog_error(e)

    def perform_create(self, serializer):
        org = resolve_request_organization(self.request)
        if not org:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {"detail": "No se pudo resolver la organización (cabecera X-Tenant)."}
            )
        serializer.save(organization=org)
        invalidate_catalog_cache(str(org.id))

    def perform_update(self, serializer):
        instance = serializer.save()
        invalidate_catalog_cache(str(instance.organization_id))

    def perform_destroy(self, instance):
        org_id = str(instance.organization_id)
        instance.delete()
        invalidate_catalog_cache(org_id)


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [PublicReadManagerWrite, IsManagerOfOrganization]
    lookup_field = "slug"
    filterset_class = ProductFilter
    search_fields = ["name", "description", "short_description", "sku"]
    ordering_fields = ["price_cop", "created_at", "name", "stock", "is_featured"]
    ordering = ["-is_featured", "-created_at"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def get_queryset(self):
        try:
            qs = Product.objects.select_related("category", "organization")
            org = _request_org(self.request)
            if org:
                qs = qs.filter(organization=org)
            if self.action in ("list", "retrieve"):
                user = self.request.user
                is_manager = (
                    getattr(user, "is_authenticated", False)
                    and getattr(user, "role", None) == "manager"
                    and getattr(user, "organization_id", None) == getattr(org, "id", None)
                )
                if not is_manager:
                    qs = qs.filter(is_published=True, is_active=True)
            return qs
        except Exception as e:
            logger.error("ProductViewSet.get_queryset failed: %s", e, exc_info=True)
            raise

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Http404:
            raise
        except APIException:
            raise
        except (DatabaseError, ProgrammingError, OperationalError) as e:
            logger.error("ProductViewSet.list DB error: %s", e, exc_info=True)
            return _catalog_error(e)
        except Exception as e:
            logger.error("ProductViewSet.list failed: %s", e, exc_info=True)
            return _catalog_error(e)

    def retrieve(self, request, *args, **kwargs):
        try:
            org = _request_org(request)
            slug = kwargs.get("slug")
            if org and slug:
                key = product_detail_cache_key(str(org.id), slug)
                try:
                    cached = cache.get(key)
                except Exception:
                    logger.exception("Cache get falló para producto")
                    cached = None
                if cached is not None:
                    return Response(cached)
                response = super().retrieve(request, *args, **kwargs)
                try:
                    if response.status_code == 200:
                        cache.set(key, response.data, 120)
                except Exception:
                    logger.exception("Cache set falló para producto")
                return response
            return super().retrieve(request, *args, **kwargs)
        except Http404:
            raise
        except APIException:
            raise
        except (DatabaseError, ProgrammingError, OperationalError) as e:
            logger.error("ProductViewSet.retrieve DB error: %s", e, exc_info=True)
            return _catalog_error(e)
        except Exception as e:
            logger.error("ProductViewSet.retrieve failed: %s", e, exc_info=True)
            return _catalog_error(e)

    def perform_create(self, serializer):
        org = resolve_request_organization(self.request)
        if not org:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {"detail": "No se pudo resolver la organización (cabecera X-Tenant)."}
            )
        product = serializer.save(organization=org)
        invalidate_catalog_cache(str(org.id), product.slug)

    def perform_update(self, serializer):
        product = serializer.save()
        invalidate_catalog_cache(str(product.organization_id), product.slug)

    def perform_destroy(self, instance):
        org_id = str(instance.organization_id)
        slug = instance.slug
        instance.delete()
        invalidate_catalog_cache(org_id, slug)


class DiscountViewSet(viewsets.ModelViewSet):
    serializer_class = DiscountSerializer
    permission_classes = [IsAuthenticated, IsManagerOrReadOnly, IsManagerOfOrganization]
    lookup_field = "code"

    def get_queryset(self):
        qs = Discount.objects.select_related("organization", "category")
        org = resolve_request_organization(self.request) or self.request.user.organization
        if org:
            qs = qs.filter(organization=org)
        return qs

    def perform_create(self, serializer):
        org = resolve_request_organization(self.request)
        if not org:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {"detail": "No se pudo resolver la organización (cabecera X-Tenant)."}
            )
        serializer.save(organization=org)


class ShopOrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ShopOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            ShopOrder.objects.filter(buyer=self.request.user)
            .prefetch_related(
                Prefetch("items", queryset=ShopOrderItem.objects.select_related("product"))
            )
            .order_by("-created_at")
        )

    @action(detail=False, methods=["post"], url_path="checkout")
    def checkout(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org = getattr(request, "current_organization", None) or request.user.organization
        if not org:
            return Response(
                {"detail": "Organización no resuelta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = create_shop_order(
                buyer=request.user,
                organization=org,
                items=serializer.validated_data["items"],
                discount_code=serializer.validated_data.get("discount_code") or None,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mp = MercadoPagoService()
            items_payload = [
                {
                    "id": str(item.product_id or item.id),
                    "title": item.product_name[:120],
                    "description": item.product_sku or item.product_name,
                    "quantity": item.quantity,
                    "currency_id": "COP",
                    "unit_price": float(item.unit_price_cop),
                }
                for item in order.items.all()
            ]
            # Si hay descuento, ajustar con ítem negativo no soportado en MP fácilmente:
            # enviamos un único ítem consolidado con el total.
            if order.discount_cop and order.discount_cop > 0:
                items_payload = [
                    {
                        "id": str(order.id),
                        "title": f"Pedido tienda ({len(items_payload)} ítems)",
                        "description": f"Descuento {order.discount_code or ''}".strip(),
                        "quantity": 1,
                        "currency_id": "COP",
                        "unit_price": float(order.total_cop),
                    }
                ]

            pref = mp.create_preference_from_items(
                items=items_payload,
                user_email=request.user.email,
                user_id=str(request.user.id),
                order_id=str(order.id),
                order_type="ecommerce",
                back_path="/tienda/resultado",
                metadata={
                    "order_type": "ecommerce",
                    "shop_order_id": str(order.id),
                    "discount_code": order.discount_code,
                },
            )
        except Exception as exc:
            logger.exception("MP shop preference failed order=%s", order.id)
            order.status = "cancelled"
            order.save(update_fields=["status", "updated_at"])
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        order.mp_preference_id = pref.get("preference_id") or ""
        order.save(update_fields=["mp_preference_id", "updated_at"])

        return Response(
            {
                "order": ShopOrderSerializer(order).data,
                "preference_id": pref.get("preference_id"),
                "init_point": pref.get("init_point"),
                "sandbox_init_point": pref.get("sandbox_init_point"),
            },
            status=status.HTTP_201_CREATED,
        )


# ShopOrderItem imported at top