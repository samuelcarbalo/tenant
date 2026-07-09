from django.urls import path, include
from rest_framework.routers import DefaultRouter

from payments.views import PaymentViewSet, mercadopago_webhook, mp_public_config

router = DefaultRouter()
router.register(r"", PaymentViewSet, basename="payments")

urlpatterns = [
    path("webhook/", mercadopago_webhook, name="mp-webhook"),
    path("config/", mp_public_config, name="mp-config"),
    path("", include(router.urls)),
]
