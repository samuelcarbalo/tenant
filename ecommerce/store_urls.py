from django.urls import path

from ecommerce.store_views import StoreLogoAPIView, StoreSettingsAPIView

app_name = "store"

urlpatterns = [
    path("settings/", StoreSettingsAPIView.as_view(), name="settings"),
    path("logo/", StoreLogoAPIView.as_view(), name="logo"),
]
