from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.sports_subscription import (
    activate_or_extend_sports_module,
    sports_module_status_payload,
    user_has_active_sports_module,
)
from payments.packages import CREDIT_COST_SPORTS_MODULE, SPORTS_MODULE_DAYS


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sports_subscription_status(request):
    payload = sports_module_status_payload(request.user)
    payload["has_access"] = user_has_active_sports_module(request.user)
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def activate_sports_subscription(request):
    """
    POST /api/v1/subscriptions/activate-sports/
    Canjea 200 créditos por 30 días de CRUD ilimitado en el Servicio de Torneos.
    """
    user = activate_or_extend_sports_module(request.user)
    return Response(
        {
            "success": True,
            "message": (
                "Suscripción al Servicio de Torneos activada. "
                f"Acceso CRUD ilimitado por {SPORTS_MODULE_DAYS} días."
            ),
            "credits": user.credits,
            "credits_spent": 0 if user.has_unlimited_credits else CREDIT_COST_SPORTS_MODULE,
            **sports_module_status_payload(user),
        },
        status=status.HTTP_200_OK,
    )
