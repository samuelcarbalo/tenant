from django.urls import path

from authentication.subscription_views import (
    activate_sports_subscription,
    sports_subscription_status,
)

urlpatterns = [
    path("activate-sports/", activate_sports_subscription, name="activate-sports-subscription"),
    path("sports-status/", sports_subscription_status, name="sports-subscription-status"),
]
