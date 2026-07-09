"""Servicios de avance entre fases y resolución de brackets."""

from django.db import transaction
from django.utils import timezone

from sports.models import Bracket, BracketNode, CompetitionGroup, Match, Team, TournamentPhase
from sports.scoring import StandingsService
from sports.scoring.match_result import MatchResultService


class SourceResolutionError(ValueError):
    pass


def resolve_team_source(source, tournament, from_phase=None):
    """Resuelve un origen de equipo (grupo, ganador de partido, etc.)."""
    if not source:
        return None

    source_type = source.get("type")
    if source_type == "team":
        return Team.objects.filter(id=source.get("team_id"), tournament=tournament).first()

    if source_type == "group_rank":
        group = CompetitionGroup.objects.filter(
            slug=source.get("group_slug"),
            phase__tournament=tournament,
        ).first()
        if not group:
            return None
        rank = int(source.get("rank", 1))
        standings = StandingsService.compute(tournament, phase=group.phase, group=group)
        if len(standings) < rank:
            return None
        return standings[rank - 1]["team"]

    if source_type == "overall_rank":
        phase = from_phase or tournament.phases.filter(slug=source.get("phase_slug")).first()
        if not phase:
            return None
        rank = int(source.get("rank", 1))
        standings = StandingsService.compute(tournament, phase=phase)
        if len(standings) < rank:
            return None
        return standings[rank - 1]["team"]

    if source_type == "bracket_winner":
        node = BracketNode.objects.filter(
            bracket__phase__tournament=tournament,
            round=source.get("round"),
            position=int(source.get("position", 1)),
        ).select_related("match").first()
        if not node or not node.match or node.match.status != "finished":
            return None
        return node.match.winner

    if source_type == "match_winner":
        match = Match.objects.filter(id=source.get("match_id"), tournament=tournament).first()
        if not match or match.status != "finished":
            return None
        return match.winner

    return None


def _validate_phase_complete(phase):
    pending = Match.objects.filter(phase=phase).exclude(status="finished").exists()
    if pending:
        raise SourceResolutionError(
            "Hay partidos sin finalizar. Completa todos los resultados antes de avanzar."
        )


def populate_knockout_nodes(bracket, tournament, posted_by, match_date=None, venue="", from_phase=None):
    """Crea o actualiza partidos de eliminatoria según los nodos del bracket."""
    if match_date is None:
        match_date = timezone.now()

    created = []
    phase = bracket.phase

    for node in bracket.nodes.select_related("match").order_by("round", "position"):
        home = resolve_team_source(node.home_source, tournament, from_phase=from_phase)
        away = resolve_team_source(node.away_source, tournament, from_phase=from_phase)
        if not home or not away:
            continue
        if home.id == away.id:
            continue

        if node.match_id:
            match = node.match
            if match.home_team_id != home.id or match.away_team_id != away.id:
                match.home_team = home
                match.away_team = away
                match.save(update_fields=["home_team", "away_team"])
            created.append(match)
            continue

        match = Match.objects.create(
            tournament=tournament,
            posted_by=posted_by,
            home_team=home,
            away_team=away,
            match_date=match_date,
            venue=venue,
            phase=phase,
            match_type="knockout",
            round_number=node.position,
            match_week=phase.order,
        )
        node.match = match
        node.save(update_fields=["match"])
        created.append(match)

    return created


@transaction.atomic
def advance_phase(tournament, from_phase_slug, posted_by, match_date=None, venue=""):
    """Cierra una fase y activa la siguiente, generando partidos de eliminatoria."""
    from_phase = tournament.phases.filter(slug=from_phase_slug).first()
    if not from_phase:
        raise SourceResolutionError("Fase de origen no encontrada.")

    next_phase = (
        tournament.phases.filter(order__gt=from_phase.order).order_by("order").first()
    )
    if not next_phase:
        raise SourceResolutionError("No hay una fase siguiente configurada.")

    _validate_phase_complete(from_phase)

    from_phase.status = "finished"
    from_phase.save(update_fields=["status"])

    next_phase.status = "active"
    next_phase.save(update_fields=["status"])

    created = []
    if next_phase.phase_type == "knockout" and hasattr(next_phase, "bracket"):
        created = populate_knockout_nodes(
            next_phase.bracket,
            tournament,
            posted_by,
            match_date=match_date,
            venue=venue,
            from_phase=from_phase,
        )

    return {
        "from_phase": from_phase,
        "next_phase": next_phase,
        "matches_created": created,
    }


def propagate_bracket_after_match(match):
    """Tras finalizar un partido de eliminatoria, llena nodos dependientes (ej. final)."""
    if match.match_type != "knockout" or not hasattr(match, "bracket_node"):
        return []

    tournament = match.tournament
    updated = []

    dependent_phases = tournament.phases.filter(
        phase_type="knockout",
        order__gt=match.phase.order,
        status__in=["pending", "active"],
    ).order_by("order")

    for phase in dependent_phases:
        if not hasattr(phase, "bracket"):
            continue
        phase.status = "active"
        phase.save(update_fields=["status"])
        matches = populate_knockout_nodes(
            phase.bracket,
            tournament,
            match.posted_by,
            match_date=match.match_date,
            venue=match.venue or "",
            from_phase=match.phase,
        )
        updated.extend(matches)

    return updated
