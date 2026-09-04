"""
Tests del módulo ecommerce.
  python manage.py test ecommerce --settings=config.settings.development -v 2
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from ecommerce.models import Category, Discount, Product, ShopOrder
from ecommerce.services import create_shop_order, fulfill_shop_order, mark_shop_order_failed
from organizations.models import Organization

API = "/api/v1/ecommerce"
TENANT = "conectando-empleo"


def auth_client(user=None):
    client = APIClient()
    client.credentials(HTTP_X_TENANT=TENANT)
    if user:
        client.force_authenticate(user=user)
    return client


class EcommerceBaseTest(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name="Shop Org", slug=TENANT)
        self.manager = User.objects.create_user(
            email="shopmgr@test.com",
            username="shopmgr",
            password="TestPass123!",
            organization=self.org,
            role="manager",
            company_name="Shop Co",
            credits=50,
            user_type="company",
        )
        self.buyer = User.objects.create_user(
            email="buyer@test.com",
            username="buyer",
            password="TestPass123!",
            organization=self.org,
            role="user",
            credits=5,
        )
        self.category = Category.objects.create(
            organization=self.org,
            name="Ropa",
            slug="ropa",
        )
        self.product = Product.objects.create(
            organization=self.org,
            category=self.category,
            name="Camiseta CAPISJ",
            slug="camiseta-capisj",
            short_description="Algodón premium",
            description="Detalle largo",
            sku="CAM-001",
            price_cop=Decimal("45000"),
            compare_at_price_cop=Decimal("55000"),
            stock=10,
            image_url="https://example.com/camisa.jpg",
            is_published=True,
            is_featured=True,
        )
        self.discount = Discount.objects.create(
            organization=self.org,
            code="SAVE10",
            name="10% off",
            discount_type=Discount.TYPE_PERCENT,
            value=Decimal("10"),
            min_order_cop=Decimal("0"),
        )
        self.anon = auth_client()
        self.manager_client = auth_client(self.manager)
        self.buyer_client = auth_client(self.buyer)


class CatalogAPITests(EcommerceBaseTest):
    def test_list_products_public(self):
        res = self.anon.get(f"{API}/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["slug"], "camiseta-capisj")

    def test_filter_by_category_and_price(self):
        res = self.anon.get(
            f"{API}/products/",
            {"category": "ropa", "min_price": 40000, "max_price": 50000},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)

    def test_product_detail(self):
        res = self.anon.get(f"{API}/products/camiseta-capisj/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["name"], "Camiseta CAPISJ")
        self.assertIn("description", res.data)
        self.assertFalse(res.data["can_manage"])

    def test_product_list_can_manage_for_admin_and_owner(self):
        self.product.created_by = self.manager
        self.product.save(update_fields=["created_by"])
        owner_list = self.manager_client.get(f"{API}/products/")
        owner_row = owner_list.data.get("results", owner_list.data)[0]
        self.assertTrue(owner_row["can_manage"])

        buyer_list = self.buyer_client.get(f"{API}/products/")
        buyer_row = buyer_list.data.get("results", buyer_list.data)[0]
        self.assertFalse(buyer_row["can_manage"])

        superuser = User.objects.create_superuser(
            email="shoproot@test.com",
            username="shoproot",
            password="TestPass123!",
        )
        root_client = auth_client(superuser)
        root_list = root_client.get(f"{API}/products/")
        root_row = root_list.data.get("results", root_list.data)[0]
        self.assertTrue(root_row["can_manage"])
        self.assertEqual(root_row["created_by"], str(self.manager.id))

    def test_mine_filter_returns_own_including_unpublished(self):
        admin = User.objects.create_user(
            email="shopadmin@test.com",
            username="shopadmin",
            password="TestPass123!",
            organization=self.org,
            role="admin",
        )
        admin_client = auth_client(admin)
        other = User.objects.create_user(
            email="other@test.com",
            username="otherseller",
            password="TestPass123!",
            organization=self.org,
            role="manager",
        )
        self.product.created_by = admin
        self.product.save(update_fields=["created_by"])
        Product.objects.create(
            organization=self.org,
            name="Oculto propio",
            slug="oculto-propio",
            price_cop=Decimal("1000"),
            stock=1,
            is_published=False,
            is_active=False,
            created_by=admin,
        )
        Product.objects.create(
            organization=self.org,
            name="De otro",
            slug="de-otro",
            price_cop=Decimal("2000"),
            stock=1,
            is_published=True,
            created_by=other,
        )

        mine = admin_client.get(f"{API}/products/", {"mine": "true"})
        self.assertEqual(mine.status_code, status.HTTP_200_OK, mine.data)
        slugs = {p["slug"] for p in mine.data.get("results", mine.data)}
        self.assertIn("camiseta-capisj", slugs)
        self.assertIn("oculto-propio", slugs)
        self.assertNotIn("de-otro", slugs)

        created_by_me = admin_client.get(
            f"{API}/products/", {"created_by_me": "true"}
        )
        self.assertEqual(created_by_me.status_code, status.HTTP_200_OK, created_by_me.data)
        self.assertEqual(
            {p["slug"] for p in created_by_me.data.get("results", created_by_me.data)},
            slugs,
        )

        by_id = admin_client.get(
            f"{API}/products/", {"created_by": str(admin.id)}
        )
        self.assertEqual(by_id.status_code, status.HTTP_200_OK, by_id.data)
        self.assertEqual(
            {p["slug"] for p in by_id.data.get("results", by_id.data)},
            slugs,
        )

        manage = admin_client.get(f"{API}/products/", {"manage": "true"})
        manage_slugs = {p["slug"] for p in manage.data.get("results", manage.data)}
        self.assertEqual(slugs, manage_slugs)

        public = self.anon.get(f"{API}/products/")
        public_slugs = {p["slug"] for p in public.data.get("results", public.data)}
        self.assertNotIn("oculto-propio", public_slugs)
        self.assertIn("de-otro", public_slugs)

        anon_mine = self.anon.get(f"{API}/products/", {"created_by_me": "true"})
        self.assertEqual(anon_mine.status_code, status.HTTP_403_FORBIDDEN)

        buyer_mine = self.buyer_client.get(f"{API}/products/", {"created_by_me": "true"})
        self.assertEqual(buyer_mine.status_code, status.HTTP_403_FORBIDDEN)

        # Manager y comprador no tienen acceso al inventario admin-only.
        manager_mine = self.manager_client.get(
            f"{API}/products/", {"created_by_me": "true"}
        )
        self.assertEqual(manager_mine.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_manage_all_lists_catalog(self):
        self.product.created_by = self.manager
        self.product.save(update_fields=["created_by"])
        Product.objects.create(
            organization=self.org,
            name="Borrador",
            slug="borrador-sa",
            price_cop=Decimal("500"),
            stock=1,
            is_published=False,
            created_by=self.manager,
        )
        superuser = User.objects.create_superuser(
            email="shopall@test.com",
            username="shopall",
            password="TestPass123!",
        )
        root_client = auth_client(superuser)
        mine = root_client.get(f"{API}/products/", {"mine": "true"})
        mine_slugs = {p["slug"] for p in mine.data.get("results", mine.data)}
        self.assertNotIn("camiseta-capisj", mine_slugs)

        listing = root_client.get(f"{API}/products/", {"manage": "true", "all": "true"})
        slugs = {p["slug"] for p in listing.data.get("results", listing.data)}
        self.assertIn("camiseta-capisj", slugs)
        self.assertIn("borrador-sa", slugs)

        own_only = root_client.get(f"{API}/products/", {"created_by_me": "true"})
        own_slugs = {p["slug"] for p in own_only.data.get("results", own_only.data)}
        self.assertNotIn("camiseta-capisj", own_slugs)

    def test_list_categories(self):
        res = self.anon.get(f"{API}/categories/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_list_products_in_stock_featured_ordering(self):
        res = self.anon.get(
            f"{API}/products/",
            {"in_stock": "true", "ordering": "-is_featured"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(results[0]["is_featured"])

    def test_product_without_category_serializes(self):
        Product.objects.create(
            organization=self.org,
            category=None,
            name="Sin categoria",
            slug="sin-categoria",
            price_cop=Decimal("10000"),
            stock=3,
            is_published=True,
        )
        res = self.anon.get(f"{API}/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        uncategorized = next(p for p in results if p["slug"] == "sin-categoria")
        self.assertIsNone(uncategorized["category_name"])
        self.assertIsNone(uncategorized["category_slug"])

    @patch.object(Category.objects, "select_related")
    def test_categories_db_error_returns_json(self, mock_select):
        from django.db.utils import ProgrammingError

        mock_select.side_effect = ProgrammingError(
            'relation "ecommerce_categories" does not exist'
        )
        res = self.anon.get(f"{API}/categories/")
        self.assertEqual(res.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(res.data.get("success"), False)
        self.assertEqual(res.data.get("results"), [])
        self.assertEqual(
            res.data.get("error"),
            "Las tablas de e-commerce no existen o no se han migrado.",
        )
        self.assertIn("ecommerce_categories", str(res.data.get("details")))

    def test_catalog_health_endpoint(self):
        res = self.anon.get(f"{API}/categories/health/")
        self.assertIn(res.status_code, (status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE))
        self.assertIn("ok", res.data)
        self.assertIn("missing_tables", res.data)

    def test_unpublished_hidden_from_public(self):
        self.product.is_published = False
        self.product.save(update_fields=["is_published"])
        res = self.anon.get(f"{API}/products/camiseta-capisj/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class OrderServiceTests(EcommerceBaseTest):
    def test_create_order_with_discount_and_stock(self):
        order = create_shop_order(
            buyer=self.buyer,
            organization=self.org,
            items=[{"product_id": self.product.id, "quantity": 2}],
            discount_code="SAVE10",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(order.subtotal_cop, Decimal("90000"))
        self.assertEqual(order.discount_cop, Decimal("9000"))
        self.assertEqual(order.shipping_cop, Decimal("0"))
        self.assertGreater(order.payment_fee_cop, Decimal("0"))
        self.assertEqual(
            order.total_cop,
            order.subtotal_cop - order.discount_cop + order.shipping_cop + order.payment_fee_cop,
        )
        self.assertEqual(order.items.count(), 1)

    def test_insufficient_stock(self):
        with self.assertRaises(ValueError):
            create_shop_order(
                buyer=self.buyer,
                organization=self.org,
                items=[{"product_id": self.product.id, "quantity": 99}],
            )

    def test_fulfill_idempotent(self):
        order = create_shop_order(
            buyer=self.buyer,
            organization=self.org,
            items=[{"product_id": self.product.id, "quantity": 1}],
        )
        self.assertTrue(fulfill_shop_order(order, "pay-1"))
        self.assertFalse(fulfill_shop_order(order, "pay-1"))
        order.refresh_from_db()
        self.assertTrue(order.fulfilled)
        self.assertEqual(order.status, "approved")
        self.discount.refresh_from_db()
        self.assertEqual(self.discount.used_count, 0)  # no discount on this order

    def test_fulfill_increments_discount_usage(self):
        order = create_shop_order(
            buyer=self.buyer,
            organization=self.org,
            items=[{"product_id": self.product.id, "quantity": 1}],
            discount_code="SAVE10",
        )
        fulfill_shop_order(order, "pay-2")
        self.discount.refresh_from_db()
        self.assertEqual(self.discount.used_count, 1)

    def test_mark_failed_restores_stock(self):
        order = create_shop_order(
            buyer=self.buyer,
            organization=self.org,
            items=[{"product_id": self.product.id, "quantity": 3}],
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)
        mark_shop_order_failed(order, "rejected", "pay-x")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)


class CheckoutAPITests(EcommerceBaseTest):
    @patch("ecommerce.views.MercadoPagoService")
    def test_checkout_creates_preference(self, MockMP):
        mock = MockMP.return_value
        mock.create_preference_from_items.return_value = {
            "preference_id": "pref-shop-1",
            "init_point": "https://mp.example/init",
            "sandbox_init_point": "https://mp.example/sandbox",
        }
        res = self.buyer_client.post(
            f"{API}/orders/checkout/",
            {
                "items": [{"product_id": str(self.product.id), "quantity": 1}],
                "discount_code": "SAVE10",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["preference_id"], "pref-shop-1")
        self.assertEqual(res.data["order"]["status"], "pending")
        self.assertEqual(res.data["currency"], "COP")
        self.assertEqual(res.data["subtotal"], 45000)
        self.assertEqual(res.data["shipping_cost"], 0)
        self.assertGreater(res.data["payment_fee"], 0)
        self.assertEqual(
            res.data["total_amount"],
            res.data["subtotal"]
            - res.data.get("discount", 0)
            + res.data["shipping_cost"]
            + res.data["payment_fee"],
        )
        self.assertTrue(ShopOrder.objects.filter(buyer=self.buyer).exists())
        mock.create_preference_from_items.assert_called_once()
        mp_items = mock.create_preference_from_items.call_args.kwargs["items"]
        titles = [item["title"] for item in mp_items]
        self.assertTrue(any("Pedido tienda" in title for title in titles))
        self.assertIn("Comisión por Procesamiento de Pago", titles)
        mp_total = sum(item["unit_price"] * item["quantity"] for item in mp_items)
        self.assertEqual(mp_total, res.data["total_amount"])

    @patch("ecommerce.views.MercadoPagoService")
    def test_checkout_includes_shipping_item_when_configured(self, MockMP):
        from ecommerce.models import StoreSettings

        StoreSettings.objects.create(
            organization=self.org,
            shipping_cost_cop=Decimal("5000"),
        )
        mock = MockMP.return_value
        mock.create_preference_from_items.return_value = {
            "preference_id": "pref-shop-ship",
            "init_point": "https://mp.example/init",
            "sandbox_init_point": "https://mp.example/sandbox",
        }
        res = self.buyer_client.post(
            f"{API}/orders/checkout/",
            {"items": [{"product_id": str(self.product.id), "quantity": 1}]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["shipping_cost"], 5000)
        titles = [
            item["title"]
            for item in mock.create_preference_from_items.call_args.kwargs["items"]
        ]
        self.assertIn("Costo de Envío", titles)
        self.assertIn("Comisión por Procesamiento de Pago", titles)
        self.assertIn("Camiseta CAPISJ", titles)

    def test_quote_returns_breakdown_without_creating_order(self):
        res = self.buyer_client.post(
            f"{API}/orders/quote/",
            {"items": [{"product_id": str(self.product.id), "quantity": 1}]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["subtotal"], 45000)
        self.assertEqual(res.data["currency"], "COP")
        self.assertGreater(res.data["payment_fee"], 0)
        self.assertFalse(ShopOrder.objects.filter(buyer=self.buyer).exists())

    def test_checkout_requires_auth(self):
        res = self.anon.post(
            f"{API}/orders/checkout/",
            {"items": [{"product_id": str(self.product.id), "quantity": 1}]},
            format="json",
        )
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class StorePublishCreditsTests(EcommerceBaseTest):
    def _payload(self, name="Producto cobrado"):
        return {
            "name": name,
            "short_description": "Test",
            "description": "Desc",
            "price_cop": "15000",
            "stock": 2,
            "category": str(self.category.id),
            "is_published": True,
        }

    def test_create_product_charges_10_credits(self):
        res = self.manager_client.post(
            f"{API}/products/",
            self._payload(),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.credits, 40)

    def test_create_product_insufficient_credits(self):
        self.manager.credits = 5
        self.manager.save(update_fields=["credits"])
        res = self.manager_client.post(
            f"{API}/products/",
            self._payload("Sin saldo"),
            format="json",
        )
        self.assertEqual(res.status_code, 402)
        self.assertIn(
            "Créditos insuficientes para publicar en la tienda.",
            str(res.data.get("detail") or res.data.get("message") or res.data),
        )
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.credits, 5)

    def test_balance_250_activates_unlimited_store(self):
        """Cualquier saldo ≥ 250 activa tienda ilimitada (no solo Paquete Diamante)."""
        self.manager.credits = 250
        self.manager.save(update_fields=["credits"])
        res = self.manager_client.post(
            f"{API}/products/",
            self._payload("Platino equivalente"),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.credits, 0)
        self.assertIsNotNone(self.manager.store_unlimited_until)

        res2 = self.manager_client.post(
            f"{API}/products/",
            self._payload("Segundo ilimitado"),
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED, res2.data)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.credits, 0)

    def test_diamond_package_first_product_activates_unlimited_store(self):
        self.manager.credits = 450
        self.manager.save(update_fields=["credits"])
        res = self.manager_client.post(
            f"{API}/products/",
            self._payload("Primero diamante"),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.credits, 200)
        self.assertIsNotNone(self.manager.store_unlimited_until)

        res2 = self.manager_client.post(
            f"{API}/products/",
            self._payload("Segundo ilimitado"),
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED, res2.data)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.credits, 200)

    def test_below_250_charges_10_per_product(self):
        self.manager.credits = 240
        self.manager.save(update_fields=["credits"])
        res = self.manager_client.post(
            f"{API}/products/",
            self._payload("Sin membresía"),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.credits, 230)
        self.assertIsNone(self.manager.store_unlimited_until)

    def test_expired_membership_reactivates_with_250_balance(self):
        from datetime import timedelta

        from django.utils import timezone

        self.manager.credits = 300
        self.manager.store_unlimited_until = timezone.now() - timedelta(days=1)
        self.manager.save(update_fields=["credits", "store_unlimited_until"])
        res = self.manager_client.post(
            f"{API}/products/",
            self._payload("Renovación"),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.credits, 50)
        self.assertIsNotNone(self.manager.store_unlimited_until)
        self.assertGreater(self.manager.store_unlimited_until, timezone.now())


class ExceptionHandlerTests(TestCase):
    def test_programming_error_returns_json_503(self):
        from django.db.utils import ProgrammingError

        from core.exceptions import custom_exception_handler

        response = custom_exception_handler(
            ProgrammingError('relation "ecommerce_products" does not exist'),
            {"view": None, "request": None},
        )
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["success"], False)
        self.assertEqual(response.data["error"][0]["field"], "database")

    def test_unhandled_error_returns_json_500(self):
        from core.exceptions import custom_exception_handler

        response = custom_exception_handler(
            RuntimeError("boom"),
            {"view": None, "request": None},
        )
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data["success"], False)
        self.assertEqual(response.data["error"][0]["field"], "server")
