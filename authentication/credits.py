from rest_framework.exceptions import ValidationError


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
