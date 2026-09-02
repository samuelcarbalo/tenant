from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from payments.packages import (
    CREDIT_COST_STORE,
    CREDIT_COST_STORE_UNLIMITED,
    STORE_UNLIMITED_DAYS,
)

INSUFFICIENT_STORE_CREDITS = "Créditos insuficientes para publicar en la tienda."


class InsufficientCredits(APIException):
    status_code = 402
    default_detail = INSUFFICIENT_STORE_CREDITS
    default_code = "insufficient_credits"


def charge_credits(user, amount: int, error_detail: str) -> int:
    """
    Cobra créditos al usuario bloqueado (select_for_update).
    Superuser / is_unlimited_credits no descuenta.
    """
    if getattr(user, "has_unlimited_credits", False):
        return user.credits
    if user.credits < amount:
        raise ValidationError({"detail": error_detail})
    user.credits -= amount
    user.save(update_fields=["credits"])
    return user.credits


def user_has_active_store_unlimited(user) -> bool:
    until = getattr(user, "store_unlimited_until", None)
    if not until:
        return False
    return until > timezone.now()


def _activate_store_unlimited_membership(user) -> int:
    """Descuenta 250 créditos del saldo y activa 30 días de tienda ilimitada."""
    user.credits -= CREDIT_COST_STORE_UNLIMITED
    user.store_unlimited_until = timezone.now() + timedelta(days=STORE_UNLIMITED_DAYS)
    pending = int(getattr(user, "store_unlimited_activations_pending", 0) or 0)
    update_fields = ["credits", "store_unlimited_until"]
    if pending > 0:
        user.store_unlimited_activations_pending = max(0, pending - 1)
        update_fields.append("store_unlimited_activations_pending")
    user.save(update_fields=update_fields)
    return user.credits


def charge_store_publish(user) -> int:
    """
    Cobro de publicación en tienda:
    - Membresía activa (store_unlimited_until > now) → 0 créditos.
    - Sin membresía y saldo ≥ 250 → descuenta 250 y activa 30 días ilimitados.
    - Sin membresía y saldo ≥ 10 → 10 créditos por producto.
    """
    if getattr(user, "has_unlimited_credits", False):
        return user.credits

    if user_has_active_store_unlimited(user):
        return user.credits

    if user.credits >= CREDIT_COST_STORE_UNLIMITED:
        return _activate_store_unlimited_membership(user)

    if user.credits >= CREDIT_COST_STORE:
        user.credits -= CREDIT_COST_STORE
        user.save(update_fields=["credits"])
        return user.credits

    raise InsufficientCredits(INSUFFICIENT_STORE_CREDITS)
