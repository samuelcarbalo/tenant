from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from authentication.models import CreditSubscriptionTransaction, User
from payments.packages import CREDIT_COST_SPORTS_MODULE, SPORTS_MODULE_DAYS

SPORTS_MODULE_EXPIRED_MESSAGE = (
    "Tu plan del Servicio de Torneos ha expirado. "
    "Por favor renueva tu suscripción por 200 créditos para seguir administrando este servicio."
)


class SportsModuleExpired(APIException):
    status_code = 403
    default_detail = SPORTS_MODULE_EXPIRED_MESSAGE
    default_code = "sports_module_expired"


def sports_module_status_payload(user) -> dict:
    active = user_has_active_sports_module(user)
    return {
        "sports_module_active": active,
        "sports_module_expires_at": getattr(user, "sports_module_expires_at", None),
        "sports_module_cost": CREDIT_COST_SPORTS_MODULE,
        "sports_module_days": SPORTS_MODULE_DAYS,
    }


def sync_sports_module_status(user) -> bool:
    """Marca sports_module_active según sports_module_expires_at > now()."""
    if not user:
        return False
    expires = getattr(user, "sports_module_expires_at", None)
    now = timezone.now()
    should_be_active = bool(expires and expires > now)
    if bool(getattr(user, "sports_module_active", False)) != should_be_active:
        user.sports_module_active = should_be_active
        try:
            user.save(update_fields=["sports_module_active"])
        except Exception:
            pass
    return should_be_active


def user_has_active_sports_module(user) -> bool:
    if not user or not getattr(user, "is_authenticated", True):
        return False
    if getattr(user, "has_unlimited_credits", False):
        return True
    if getattr(user, "is_superuser", False):
        return True
    try:
        from core.permissions import _is_sports_super_admin

        if _is_sports_super_admin(user):
            return True
    except Exception:
        pass
    return sync_sports_module_status(user)


@transaction.atomic
def activate_or_extend_sports_module(user: User) -> User:
    """
    Canjea 200 créditos por 30 días de CRUD ilimitado en Deportes.
    Si la suscripción sigue vigente, extiende desde sports_module_expires_at.
    Si está vencida o no existe, inicia desde now().
    Superuser / créditos ilimitados no descuentan saldo.
    """
    fresh = User.objects.select_for_update().get(id=user.id)
    now = timezone.now()
    credits_spent = 0

    if not getattr(fresh, "has_unlimited_credits", False):
        if fresh.credits < CREDIT_COST_SPORTS_MODULE:
            raise ValidationError(
                {
                    "detail": (
                        f"Necesitas {CREDIT_COST_SPORTS_MODULE} créditos para activar el "
                        f"Servicio de Torneos. Actualmente tienes {fresh.credits} créditos."
                    )
                }
            )
        fresh.credits -= CREDIT_COST_SPORTS_MODULE
        credits_spent = CREDIT_COST_SPORTS_MODULE

    current_exp = fresh.sports_module_expires_at
    if current_exp and current_exp > now:
        new_exp = current_exp + timedelta(days=SPORTS_MODULE_DAYS)
    else:
        new_exp = now + timedelta(days=SPORTS_MODULE_DAYS)

    fresh.sports_module_expires_at = new_exp
    fresh.sports_module_active = True
    fresh.save(
        update_fields=["credits", "sports_module_expires_at", "sports_module_active"]
    )

    CreditSubscriptionTransaction.objects.create(
        user=fresh,
        transaction_type=CreditSubscriptionTransaction.TYPE_SPORTS_MODULE,
        credits_spent=credits_spent,
        days_granted=SPORTS_MODULE_DAYS,
        expires_at=new_exp,
        notes="Canje de suscripción mensual al Servicio de Torneos",
    )
    return fresh


def expire_stale_sports_modules() -> int:
    """Job diario: apaga suscripciones cuya fecha ya venció."""
    now = timezone.now()
    return User.objects.filter(
        sports_module_active=True,
    ).filter(
        models_q_expired(now)
    ).update(sports_module_active=False)


def models_q_expired(now):
    from django.db.models import Q

    return Q(sports_module_expires_at__isnull=True) | Q(sports_module_expires_at__lte=now)
