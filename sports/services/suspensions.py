"""Lógica de suspensiones de jugadores (automáticas y manuales)."""
from django.db.models import Q

from sports.models import Match, Player, PlayerSuspension


def _team_matches_after_sanction(suspension: PlayerSuspension):
    """Partidos del equipo del jugador posteriores al partido sancionado."""
    player = suspension.player
    team = player.team
    qs = Match.objects.filter(tournament=suspension.tournament).filter(
        Q(home_team=team) | Q(away_team=team)
    ).exclude(status="cancelled")

    if suspension.match_id:
        ref = suspension.match
        qs = qs.filter(
            Q(match_date__gt=ref.match_date)
            | Q(match_date=ref.match_date, id__gt=ref.id)
        )

    return qs.order_by("match_date", "id")


def get_affected_match_ids(suspension: PlayerSuspension) -> list:
    """IDs de partidos que el jugador debe cumplir según fechas restantes."""
    remaining = max(0, suspension.matches_count - suspension.matches_served)
    if remaining <= 0 or not suspension.is_active:
        return []
    return list(_team_matches_after_sanction(suspension)[:remaining].values_list("id", flat=True))


def is_player_suspended_for_match(player: Player, match: Match) -> tuple[bool, PlayerSuspension | None]:
    """Indica si el jugador está inhabilitado para un partido concreto."""
    if not player or not match:
        return False, None

    suspensions = PlayerSuspension.objects.filter(
        player=player,
        tournament=match.tournament,
        is_active=True,
    )
    for suspension in suspensions:
        if match.id in get_affected_match_ids(suspension):
            return True, suspension
    return False, None


def process_suspensions_on_match_finish(match: Match) -> None:
    """Al finalizar un partido, descuenta fechas cumplidas de las sanciones activas."""
    if match.status != "finished":
        return

    team_ids = [match.home_team_id, match.away_team_id]
    players = Player.objects.filter(team_id__in=team_ids, tournament=match.tournament)

    for player in players:
        for suspension in PlayerSuspension.objects.filter(
            player=player, tournament=match.tournament, is_active=True
        ):
            affected = get_affected_match_ids(suspension)
            if not affected or affected[0] != match.id:
                continue

            suspension.matches_served += 1
            if suspension.matches_served >= suspension.matches_count:
                suspension.is_active = False
            suspension.save(update_fields=["matches_served", "is_active", "updated_at"])


def create_player_suspension(
    *,
    player: Player,
    match: Match | None,
    reason: str,
    notes: str,
    created_by,
    matches_count: int = 1,
) -> PlayerSuspension | None:
    """Crea una suspensión evitando duplicados activos del mismo motivo en el mismo partido."""
    if not player or not player.tournament:
        return None

    if match and PlayerSuspension.objects.filter(
        player=player,
        tournament=player.tournament,
        match=match,
        reason=reason,
        is_active=True,
    ).exists():
        return None

    next_match = None
    if match:
        next_match = (
            _team_matches_after_sanction(
                PlayerSuspension(player=player, tournament=player.tournament, match=match)
            ).first()
        )

    return PlayerSuspension.objects.create(
        player=player,
        tournament=player.tournament,
        match=match,
        suspended_until_match=next_match,
        reason=reason,
        matches_count=max(1, matches_count),
        matches_served=0,
        notes=notes,
        created_by=created_by,
        is_active=True,
    )
