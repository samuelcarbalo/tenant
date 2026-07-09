"""Servicios para estructura de torneos y generación de fixture."""

from itertools import combinations

from django.utils.text import slugify

from sports.formats.templates import get_template
from sports.models import (
    CompetitionGroup,
    GroupMembership,
    Match,
    Tournament,
    TournamentPhase,
    Bracket,
    BracketNode,
)


def apply_format_template(tournament: Tournament, template_id: str, group_count: int = 1):
    """Crea fases y grupos según plantilla."""
    template = get_template(template_id)
    if not template:
        return

    tournament.structure_mode = template.get("structure_mode", "structured")
    tournament.format_template = template_id
    if template.get("default_max_teams"):
        tournament.max_teams = template["default_max_teams"]
    tournament.save(
        update_fields=["structure_mode", "format_template", "max_teams"]
    )

    for phase_def in template.get("phases", []):
        phase = TournamentPhase.objects.create(
            tournament=tournament,
            name=phase_def["name"],
            slug=phase_def["slug"],
            phase_type=phase_def["phase_type"],
            order=phase_def.get("order", 1),
            status="active" if phase_def.get("order", 1) == 1 else "pending",
            config=phase_def.get("config", {}),
            advancement_rules=phase_def.get("advancement_rules", {}),
        )

        if phase_def.get("groups_auto"):
            teams_per = phase_def.get("config", {}).get("teams_per_group", 4)
            for i in range(group_count):
                letter = chr(ord("A") + i)
                CompetitionGroup.objects.create(
                    phase=phase,
                    name=f"Cuadrangular {letter}",
                    slug=slugify(f"cuadrangular-{letter}"),
                    order=i + 1,
                    max_teams=teams_per,
                )
        else:
            for idx, group_def in enumerate(phase_def.get("groups", []), start=1):
                CompetitionGroup.objects.create(
                    phase=phase,
                    name=group_def["name"],
                    slug=group_def["slug"],
                    order=idx,
                    max_teams=group_def.get("max_teams", 4),
                )

        if phase_def.get("phase_type") == "knockout" or phase_def.get("bracket"):
            _create_bracket_for_phase(phase, phase_def.get("bracket", {}))


def _create_bracket_for_phase(phase: TournamentPhase, bracket_def: dict):
    bracket = Bracket.objects.create(
        phase=phase,
        name=bracket_def.get("name", phase.name),
    )
    for node_def in bracket_def.get("nodes", []):
        BracketNode.objects.create(
            bracket=bracket,
            round=node_def["round"],
            position=node_def.get("position", 1),
            home_source=node_def.get("home_source", {}),
            away_source=node_def.get("away_source", {}),
        )


def assign_teams_to_group(group: CompetitionGroup, team_ids: list):
    """Asigna equipos a un grupo (reemplaza membresías existentes)."""
    group.memberships.all().delete()
    memberships = []
    for idx, team_id in enumerate(team_ids, start=1):
        memberships.append(
            GroupMembership(group=group, team_id=team_id, seed=idx)
        )
    GroupMembership.objects.bulk_create(memberships)


def generate_round_robin_fixtures(
    tournament: Tournament,
    phase: TournamentPhase,
    group,
    posted_by,
    match_date,
    venue: str = "",
):
    """Genera partidos round-robin para un grupo o fase sin grupos."""
    if group:
        teams = [m.team for m in group.memberships.select_related("team")]
    else:
        teams = list(tournament.teams.all())

    if len(teams) < 2:
        raise ValueError("Se necesitan al menos 2 equipos para generar el fixture.")

    created = []
    round_num = 1
    for home, away in combinations(teams, 2):
        match = Match.objects.create(
            tournament=tournament,
            posted_by=posted_by,
            home_team=home,
            away_team=away,
            match_date=match_date,
            venue=venue,
            phase=phase,
            group=group,
            match_type="group" if group or phase.phase_type in ("group_stage", "round_robin") else "legacy",
            round_number=round_num,
            match_week=1,
        )
        created.append(match)
        round_num += 1
    return created
