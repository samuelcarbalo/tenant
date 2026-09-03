from rest_framework.permissions import SAFE_METHODS

from authentication.sports_subscription import (
    SportsModuleExpired,
    user_has_active_sports_module,
)

SPORTS_WRITE_EXEMPT_ACTIONS = frozenset(
    {
        "track_click",
        "by_position",
        "active",
        "positions",
        "config",
    }
)


def _tournament_from_obj(obj):
    if obj is None:
        return None
    if obj.__class__.__name__ == "Tournament":
        return obj
    return getattr(obj, "tournament", None)


def resolve_related_tournament(request, view):
    from sports.models import (
        AdvertisementBanner,
        Match,
        Player,
        PlayerSuspension,
        Team,
        Tournament,
    )

    kwargs = getattr(view, "kwargs", {}) or {}
    slug = kwargs.get("slug")
    if slug:
        tournament = (
            Tournament.objects.select_related("posted_by").filter(slug=slug).first()
        )
        if tournament:
            return tournament

    pk = kwargs.get("pk")
    if pk:
        for model in (Team, Player, Match, PlayerSuspension, AdvertisementBanner):
            obj = model.objects.select_related("tournament", "tournament__posted_by").filter(
                pk=pk
            ).first()
            if obj:
                return _tournament_from_obj(obj)

    data = getattr(request, "data", None)
    if isinstance(data, dict):
        raw = data.get("tournament") or data.get("tournament_id")
        if raw:
            qs = Tournament.objects.select_related("posted_by")
            tournament = qs.filter(id=raw).first() or qs.filter(slug=str(raw)).first()
            if tournament:
                return tournament
        team_id = data.get("team")
        if team_id:
            team = Team.objects.select_related("tournament", "tournament__posted_by").filter(
                id=team_id
            ).first()
            if team:
                return team.tournament
    return None


def request_can_write_sports(request, view) -> bool:
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if user_has_active_sports_module(user):
        return True
    tournament = resolve_related_tournament(request, view)
    owner = getattr(tournament, "posted_by", None) if tournament else None
    if owner and user_has_active_sports_module(owner):
        return True
    return False


class SportsSubscriptionGuardMixin:
    """
    Bloquea POST/PUT/PATCH/DELETE del módulo de Deportes si no hay
    suscripción vigente (usuario o dueño del torneo). GET permanece público.
    Super Admin / créditos ilimitados siempre pasan.
    """

    def check_permissions(self, request):
        super().check_permissions(request)
        action = getattr(self, "action", None)
        if action in SPORTS_WRITE_EXEMPT_ACTIONS:
            return
        if request.method in SAFE_METHODS:
            return
        if request_can_write_sports(request, self):
            return
        raise SportsModuleExpired()
