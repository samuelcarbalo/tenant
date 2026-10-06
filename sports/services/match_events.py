"""Efectos de un evento de partido sobre el marcador y las estadísticas."""

from django.db import transaction
from django.utils import timezone

from sports.models import Match, Player, PlayerSuspension

# Tipos que suman al marcador global de fútbol.
_GOAL_FOR_TEAM = frozenset({"goal", "penalty_goal"})
_OWN_GOAL = "own_goal"


def _clamp_add(player, field, amount):
    setattr(player, field, max(0, (getattr(player, field) or 0) + amount))


def score_deltas(event):
    """
    (home_delta, away_delta) de un evento de fútbol.
    En softbol el marcador sale del line score, no de los eventos.
    """
    match = event.match
    tournament = getattr(match, "tournament", None)
    if tournament is None or getattr(tournament, "sport_type", None) == "softball":
        return 0, 0

    team_id = event.team_id
    home_id = match.home_team_id
    away_id = match.away_team_id
    if event.event_type == _OWN_GOAL:
        if team_id == home_id:
            return 0, 1
        if team_id == away_id:
            return 1, 0
        return 0, 0
    if event.event_type in _GOAL_FOR_TEAM:
        if team_id == home_id:
            return 1, 0
        if team_id == away_id:
            return 0, 1
    return 0, 0


def apply_event_score(event, delta=1):
    """Suma o resta el efecto del evento sobre home_score y away_score."""
    home_delta, away_delta = score_deltas(event)
    home_delta *= delta
    away_delta *= delta
    if home_delta == 0 and away_delta == 0:
        return event.match

    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=event.match_id)
        match.home_score = max(0, (match.home_score or 0) + home_delta)
        match.away_score = max(0, (match.away_score or 0) + away_delta)
        match.save(update_fields=["home_score", "away_score"])

    event.match.home_score = match.home_score
    event.match.away_score = match.away_score
    return event.match


def apply_event_player_stats(event, delta=1):
    """Aplica o revierte las estadísticas del jugador asociadas al evento."""
    if event.player_id is None or not delta:
        return

    sport = event.match.tournament.sport_type
    with transaction.atomic():
        player = Player.objects.select_for_update().get(pk=event.player_id)
        if sport == "softball":
            _apply_softball_stats(player, event, delta)
        else:
            _apply_football_stats(player, event, delta)
        player.save()


def _apply_football_stats(player, event, delta):
    if event.event_type in ("goal", "penalty_goal"):
        _clamp_add(player, "goals", delta)
    elif event.event_type == "yellow_card":
        _clamp_add(player, "yellow_cards", delta)
    elif event.event_type == "red_card":
        _clamp_add(player, "red_cards", delta)


def _apply_softball_stats(player, event, delta):
    event_type = event.event_type
    if event_type in ("single", "double", "triple", "home_run"):
        _clamp_add(player, "hits", delta)
        _clamp_add(player, "at_bats", delta)
        if event_type == "home_run":
            _clamp_add(player, "home_runs", delta)
    elif event_type == "strikeout":
        _clamp_add(player, "strikes_out", delta)
        _clamp_add(player, "at_bats", delta)
    elif event_type == "out":
        _clamp_add(player, "at_bats", delta)
    elif event_type == "walk":
        _clamp_add(player, "walks", delta)
    elif event_type == "run":
        _clamp_add(player, "runs_scored", delta)
    elif event_type == "rbi":
        _clamp_add(player, "rbis", delta * max(1, event.rbi or 0))

    player.batting_average = (
        player.hits / player.at_bats if player.at_bats > 0 else 0.0
    )


def revoke_red_card_suspension(*, player_id, match_id, user):
    """Anula la sanción automática ligada a una roja que se corrige o se borra."""
    if not player_id or not match_id:
        return
    now = timezone.now()
    PlayerSuspension.objects.filter(
        player_id=player_id,
        match_id=match_id,
        reason__in=("direct_red", "double_yellow"),
        is_active=True,
    ).update(
        is_active=False,
        revoked_at=now,
        revoked_by=user if getattr(user, "pk", None) else None,
        updated_at=now,
    )
