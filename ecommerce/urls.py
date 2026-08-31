from django.urls import include, path
from rest_framework.routers import DefaultRouter

from ecommerce.views import (
    CategoryViewSet,
    DiscountViewSet,
    ProductViewSet,
    ShopOrderViewSet,
    SubCategoryViewSet,
)

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="shop-category")
router.register(r"subcategories", SubCategoryViewSet, basename="shop-subcategory")
router.register(r"products", ProductViewSet, basename="shop-product")
router.register(r"discounts", DiscountViewSet, basename="shop-discount")
router.register(r"orders", ShopOrderViewSet, basename="shop-order")

urlpatterns = [
    path("", include(router.urls)),
]
