import logging

from django.core.cache import cache
from django.db import DatabaseError
from django.db.utils import OperationalError, ProgrammingError
from django.http import Http404
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response

from ecommerce.batch_import import (
    MAX_BATCH_ROWS,
    MAX_UPLOAD_BYTES,
    PRODUCT_HEADERS,
    assert_product_headers,
    import_products_batch,
    read_upload_rows,
    template_http_response,
)
from ecommerce.models import (
    Category,
    Discount,
    Product,
    ProductDiscount,
    ShopInvoice,
    ShopOrder,
    ShopOrderItem,
    SubCategory,
)
from ecommerce.serializers import (
    CategorySerializer,
    CheckoutSerializer,
    DiscountSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductWriteSerializer,
    ShopOrderSerializer,
    SubCategorySerializer,
)
from ecommerce.checkout import (
    build_mp_preference_items,
    checkout_payload_from_order,
    checkout_public_payload,
)
from ecommerce.services import (
    categories_cache_key,
    create_shop_order,
    invalidate_catalog_cache,
    product_detail_cache_key,
    quote_shop_checkout,
)
from core.permissions import (
    CanManageShopProduct,
    resolve_request_organization,
    user_can_manage_content,
    user_can_manage_shop_product,
    user_can_query_own_shop_products,
    user_is_platform_elevated,
    user_is_shop_super_admin,
)
from jobs.permissions import IsManagerOfOrganization, IsManagerOrReadOnly
from payments.services.mercadopago_service import MercadoPagoService

logger = logging.getLogger(__name__)

_MISSING_TABLE_MSG = "Las tablas de e-commerce no existen o no se han migrado."


def _query_flag(request, *names: str) -> bool:
    params = getattr(request, "query_params", None) or {}
    for name in names:
        raw = str(params.get(name) or "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
    return False


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
    category_id = filters.UUIDFilter(field_name="category_id")
    subcategory = filters.CharFilter(field_name="subcategory__slug")
    min_price = filters.NumberFilter(field_name="price_cop", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price_cop", lookup_expr="lte")
    featured = filters.BooleanFilter(field_name="is_featured")
    in_stock = filters.BooleanFilter(method="filter_in_stock")
    flash_sale = filters.BooleanFilter(method="filter_flash_sale")

    class Meta:
        model = Product
        fields = ["category", "category_id", "subcategory", "min_price", "max_price", "featured"]

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock__gt=0)
        return queryset

    def filter_flash_sale(self, queryset, name, value):
        if not value:
            return queryset
        from django.utils import timezone as tz

        now = tz.now()
        return queryset.filter(
            product_discounts__is_active=True,
            product_discounts__is_flash_sale=True,
            product_discounts__start_time__lte=now,
            product_discounts__end_time__gte=now,
        ).distinct()


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


class SubCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = SubCategorySerializer
    permission_classes = [PublicReadManagerWrite, IsManagerOfOrganization]
    lookup_field = "slug"
    search_fields = ["name", "description"]
    ordering_fields = ["sort_order", "name", "created_at"]
    ordering = ["sort_order", "name"]

    def get_queryset(self):
        qs = SubCategory.objects.select_related("organization", "category")
        org = _request_org(self.request)
        if org:
            qs = qs.filter(organization=org)
        category_slug = self.request.query_params.get("category")
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        if self.action in ("list", "retrieve"):
            qs = qs.filter(is_active=True)
        return qs

    def perform_create(self, serializer):
        org = resolve_request_organization(self.request)
        if not org:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {"detail": "No se pudo resolver la organización (cabecera X-Tenant)."}
            )
        serializer.save(organization=org)


SHOP_PRODUCT_FORBIDDEN = {
    "message": "No tienes permisos para editar o eliminar este producto.",
    "detail": "No tienes permisos para editar o eliminar este producto.",
}

SHOP_INVENTORY_FORBIDDEN = (
    "No tienes permisos de vendedor o administrador para consultar productos creados."
)


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [CanManageShopProduct]
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
            qs = Product.objects.select_related(
                "category", "subcategory", "organization", "created_by"
            ).prefetch_related("product_discounts")
            org = _request_org(self.request)
            if org:
                qs = qs.filter(organization=org)
            if self.action not in ("list", "retrieve"):
                return qs

            user = self.request.user
            mine = _query_flag(self.request, "mine", "my_products", "created_by_me")
            manage = _query_flag(self.request, "manage")
            see_all = _query_flag(self.request, "all")
            created_by = str(self.request.query_params.get("created_by") or "").strip()

            # Inventario: incluye no publicados. El catálogo público no usa estos flags.
            if mine or manage or created_by:
                if not user_can_query_own_shop_products(user):
                    raise PermissionDenied(SHOP_INVENTORY_FORBIDDEN)
                is_sa = user_is_shop_super_admin(user)
                if created_by:
                    from uuid import UUID

                    try:
                        creator_id = UUID(created_by)
                    except (ValueError, TypeError, AttributeError):
                        return qs.none()
                    if str(getattr(user, "id", "")) != str(creator_id) and not is_sa:
                        raise PermissionDenied(SHOP_INVENTORY_FORBIDDEN)
                    return qs.filter(created_by_id=creator_id)
                if mine or not (is_sa and see_all):
                    qs = qs.filter(created_by_id=user.id)
                return qs

            if user_is_shop_super_admin(user):
                return qs
            is_manager = (
                getattr(user, "is_authenticated", False)
                and getattr(user, "role", None) == "manager"
                and getattr(user, "organization_id", None) == getattr(org, "id", None)
            )
            if not is_manager:
                qs = qs.filter(is_published=True, is_active=True)
            return qs
        except (Http404, APIException):
            raise
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

    def _forbid_if_cannot_manage(self, product):
        if user_can_manage_shop_product(self.request.user, product):
            return None
        return Response(SHOP_PRODUCT_FORBIDDEN, status=status.HTTP_403_FORBIDDEN)

    def retrieve(self, request, *args, **kwargs):
        try:
            org = _request_org(request)
            slug = kwargs.get("slug")
            # No cachear para usuarios autenticados: can_manage es por usuario.
            if org and slug and not (request.user and request.user.is_authenticated):
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
        product = serializer.save(organization=org, created_by=self.request.user)
        invalidate_catalog_cache(str(org.id), product.slug)

    def update(self, request, *args, **kwargs):
        product = self.get_object()
        denied = self._forbid_if_cannot_manage(product)
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        product = self.get_object()
        denied = self._forbid_if_cannot_manage(product)
        if denied:
            return denied
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        denied = self._forbid_if_cannot_manage(product)
        if denied:
            return denied
        return super().destroy(request, *args, **kwargs)

    def perform_update(self, serializer):
        product = serializer.save()
        invalidate_catalog_cache(str(product.organization_id), product.slug)

    def perform_destroy(self, instance):
        org_id = str(instance.organization_id)
        slug = instance.slug
        instance.delete()
        invalidate_catalog_cache(org_id, slug)

    @action(detail=True, methods=["patch"], url_path="status")
    def set_status(self, request, slug=None):
        product = self.get_object()
        denied = self._forbid_if_cannot_manage(product)
        if denied:
            return denied
        data = request.data or {}
        update_fields = ["updated_at"]
        if "is_published" in data:
            product.is_published = bool(data.get("is_published"))
            update_fields.append("is_published")
        if "is_active" in data:
            product.is_active = bool(data.get("is_active"))
            update_fields.append("is_active")
        if "stock" in data:
            try:
                stock = int(data.get("stock"))
            except (TypeError, ValueError):
                return Response(
                    {"detail": "Stock inválido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if stock < 0:
                return Response(
                    {"detail": "Stock inválido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            product.stock = stock
            update_fields.append("stock")
        product.save(update_fields=update_fields)
        invalidate_catalog_cache(str(product.organization_id), product.slug)
        return Response(ProductDetailSerializer(product, context={"request": request}).data)

    @action(
        detail=False,
        methods=["get"],
        url_path="import-template",
        permission_classes=[IsAuthenticated],
    )
    def import_template(self, request):
        """Descarga plantilla CSV/XLSX de productos (solo admin inventario)."""
        if not user_can_query_own_shop_products(request.user):
            raise PermissionDenied(SHOP_INVENTORY_FORBIDDEN)
        fmt = str(request.query_params.get("format") or "xlsx").lower()
        response = template_http_response(fmt=fmt)
        response["X-Batch-Max-Rows"] = str(MAX_BATCH_ROWS)
        response["X-Batch-Max-Bytes"] = str(MAX_UPLOAD_BYTES)
        response["X-Template-Headers"] = ",".join(PRODUCT_HEADERS)
        return response

    @action(
        detail=False,
        methods=["post"],
        url_path="import-batch",
        permission_classes=[IsAuthenticated],
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_batch(self, request):
        """
        Carga masiva CSV/XLSX. Límites Free: 2 MB / 200 filas.
        Asocia productos a organization (X-Tenant) y created_by=request.user.
        """
        if not user_can_query_own_shop_products(request.user):
            raise PermissionDenied(SHOP_INVENTORY_FORBIDDEN)

        upload = request.FILES.get("file") or request.FILES.get("excel")
        if not upload:
            return Response(
                {
                    "status": "error",
                    "message": "Adjunte el archivo en el campo 'file' (.csv o .xlsx).",
                    "max_rows": MAX_BATCH_ROWS,
                    "max_bytes": MAX_UPLOAD_BYTES,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        size = int(getattr(upload, "size", 0) or 0)
        if size > MAX_UPLOAD_BYTES:
            return Response(
                {
                    "status": "error",
                    "message": (
                        f"El archivo supera el máximo de "
                        f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB del plan actual."
                    ),
                    "max_bytes": MAX_UPLOAD_BYTES,
                    "max_rows": MAX_BATCH_ROWS,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = resolve_request_organization(request)
        if org is None:
            return Response(
                {
                    "status": "error",
                    "message": "No se pudo resolver la organización (cabecera X-Tenant).",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            headers, rows = read_upload_rows(upload)
            assert_product_headers(headers)
            if not rows:
                return Response(
                    {
                        "status": "error",
                        "message": "El archivo no contiene filas de productos.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            result = import_products_batch(
                rows=rows, organization=org, user=request.user
            )
        except ValueError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                    "max_rows": MAX_BATCH_ROWS,
                    "max_bytes": MAX_UPLOAD_BYTES,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("import-batch falló")
            return Response(
                {
                    "status": "error",
                    "message": f"No se pudo procesar el archivo: {exc}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invalidate_catalog_cache(str(org.id))
        except Exception:
            logger.exception("No se pudo invalidar caché tras import-batch")

        payload = {
            "status": "ok" if not result.errors else "partial",
            "success": True,
            "message": "Importación completada.",
            "organization": getattr(org, "slug", None),
            "max_rows": MAX_BATCH_ROWS,
            "max_bytes": MAX_UPLOAD_BYTES,
            "headers": PRODUCT_HEADERS,
            **result.as_dict(),
        }
        if result.errors and result.created + result.updated == 0:
            payload["status"] = "error"
            payload["success"] = False
            payload["message"] = "Se encontraron errores al procesar el archivo."
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_200_OK)


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

    def _base_qs(self):
        return ShopOrder.objects.select_related(
            "buyer", "organization", "invoice"
        ).prefetch_related(
            Prefetch("items", queryset=ShopOrderItem.objects.select_related("product"))
        )

    def get_queryset(self):
        qs = self._base_qs().order_by("-created_at")
        user = self.request.user
        if self.action in ("sales", "metrics", "set_delivery"):
            if not user_can_manage_content(user):
                return qs.none()
            if user_is_platform_elevated(user):
                return qs
            org = resolve_request_organization(self.request) or getattr(user, "organization", None)
            if not org:
                return qs.none()
            return qs.filter(organization=org)
        if self.action == "retrieve" and user_can_manage_content(user):
            if user_is_platform_elevated(user):
                return qs
            org = resolve_request_organization(self.request) or getattr(user, "organization", None)
            if org:
                return qs.filter(Q(buyer=user) | Q(organization=org))
        return qs.filter(buyer=user)

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        from ecommerce.invoices import sync_shop_invoice

        if not ShopInvoice.objects.filter(order=order).exists():
            try:
                sync_shop_invoice(order)
                order.refresh_from_db()
            except Exception:
                logger.exception("invoice sync failed order=%s", order.id)
        return Response(ShopOrderSerializer(order).data)

    def _apply_sales_filters(self, qs):
        params = self.request.query_params
        status_val = (params.get("status") or "").strip()
        delivery = (params.get("delivery_status") or "").strip()
        search = (params.get("search") or "").strip()
        date_from = (params.get("date_from") or "").strip()
        date_to = (params.get("date_to") or "").strip()
        if status_val:
            qs = qs.filter(status=status_val)
        if delivery:
            qs = qs.filter(delivery_status=delivery)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if search:
            qs = qs.filter(
                Q(buyer__email__icontains=search)
                | Q(buyer__first_name__icontains=search)
                | Q(buyer__last_name__icontains=search)
                | Q(invoice__number__icontains=search)
                | Q(items__product_name__icontains=search)
            ).distinct()
        return qs

    @action(detail=False, methods=["get"], url_path="sales")
    def sales(self, request):
        if not user_can_manage_content(request.user):
            return Response(
                {"detail": "No tienes permiso para ver las ventas de la tienda."},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = self._apply_sales_filters(self.get_queryset())
        page = self.paginate_queryset(qs)
        serializer = ShopOrderSerializer(page if page is not None else qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="metrics")
    def metrics(self, request):
        if not user_can_manage_content(request.user):
            return Response(
                {"detail": "No tienes permiso para ver métricas de ventas."},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = self.get_queryset().filter(status="approved")
        date_from = (request.query_params.get("date_from") or "").strip()
        date_to = (request.query_params.get("date_to") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        agg = qs.aggregate(
            total_sales=Sum("total_cop"),
            order_count=Count("id"),
            avg_ticket=Avg("total_cop"),
        )
        top = list(
            ShopOrderItem.objects.filter(order__in=qs)
            .values("product_name")
            .annotate(quantity=Sum("quantity"), revenue=Sum("line_total_cop"))
            .order_by("-quantity")[:8]
        )
        return Response(
            {
                "total_sales_cop": agg["total_sales"] or 0,
                "order_count": agg["order_count"] or 0,
                "avg_ticket_cop": agg["avg_ticket"] or 0,
                "top_sellers": top,
            }
        )

    @action(detail=True, methods=["patch"], url_path="delivery")
    def set_delivery(self, request, pk=None):
        if not user_can_manage_content(request.user):
            return Response(
                {"detail": "No tienes permiso para actualizar el envío."},
                status=status.HTTP_403_FORBIDDEN,
            )
        order = self.get_object()
        next_status = (request.data.get("delivery_status") or "").strip()
        allowed = {c[0] for c in ShopOrder.DELIVERY_CHOICES}
        if next_status not in allowed:
            return Response(
                {"detail": "Estado de envío inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.delivery_status = next_status
        order.save(update_fields=["delivery_status", "updated_at"])
        return Response(ShopOrderSerializer(order).data)

    @action(detail=False, methods=["post"], url_path="quote")
    def quote(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org = getattr(request, "current_organization", None) or request.user.organization
        if not org:
            return Response(
                {"detail": "Organización no resuelta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            totals = quote_shop_checkout(
                organization=org,
                items=serializer.validated_data["items"],
                discount_code=serializer.validated_data.get("discount_code") or None,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(checkout_public_payload(totals))

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
            items_payload = build_mp_preference_items(order)
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
                    "subtotal": str(order.subtotal_cop),
                    "shipping_cost": str(order.shipping_cop),
                    "payment_fee": str(order.payment_fee_cop),
                    "total_amount": str(order.total_cop),
                },
            )
        except Exception as exc:
            logger.exception("MP shop preference failed order=%s", order.id)
            order.status = "cancelled"
            order.save(update_fields=["status", "updated_at"])
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        order.mp_preference_id = pref.get("preference_id") or ""
        order.save(update_fields=["mp_preference_id", "updated_at"])

        payload = checkout_payload_from_order(order)
        payload.update(
            {
                "order": ShopOrderSerializer(order).data,
                "preference_id": pref.get("preference_id"),
                "init_point": pref.get("init_point"),
                "sandbox_init_point": pref.get("sandbox_init_point"),
                "is_production": pref.get("is_production", mp.is_production),
            }
        )
        return Response(payload, status=status.HTTP_201_CREATED)


# ShopOrderItem imported at top
