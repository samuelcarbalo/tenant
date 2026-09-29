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
    auto_phases = [p for p in template.get("phases", []) if p.get("groups_auto")]
    if auto_phases:
        teams_per = auto_phases[0].get("config", {}).get("teams_per_group", 4)
        requested = max(1, int(group_count or 1))
        if template.get("dynamic_playoff"):
            group_count = min(16, max(2, requested))
        else:
            group_count = min(16, requested)
        tournament.max_teams = group_count * teams_per
    elif template.get("default_max_teams"):
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
                    name=f"Grupo {letter}",
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

    if template.get("dynamic_playoff"):
        _append_dynamic_playoff(tournament, group_count)


def _group_letter(index: int) -> str:
    return chr(ord("a") + index)


def _playoff_round_meta(match_count: int):
    named = {
        1: ("final", "final", "Final"),
        2: ("semifinal", "semifinales", "Semifinales"),
        4: ("quarterfinal", "cuartos", "Cuartos de final"),
        8: ("round_of_16", "octavos", "Octavos de final"),
        16: ("round_of_32", "dieciseisavos", "Dieciseisavos de final"),
    }
    if match_count in named:
        return named[match_count]
    return (f"round_{match_count}", f"ronda-{match_count}", f"Ronda de {match_count}")


def _cross_group_pairings(group_count: int):
    """1.º del grupo i contra 2.º del grupo siguiente."""
    pairings = []
    for i in range(group_count):
        home = _group_letter(i)
        away = _group_letter((i + 1) % group_count)
        pairings.append(
            (
                {"type": "group_rank", "group_slug": f"cuadrangular-{home}", "rank": 1},
                {"type": "group_rank", "group_slug": f"cuadrangular-{away}", "rank": 2},
            )
        )
    return pairings


def _next_round_pairings(previous_round_code: str, node_count: int):
    pairings = []
    index = 1
    while index <= node_count:
        home = {"type": "bracket_winner", "round": previous_round_code, "position": index}
        if index + 1 <= node_count:
            away = {
                "type": "bracket_winner",
                "round": previous_round_code,
                "position": index + 1,
            }
            index += 2
        else:
            away = {"type": "bye"}
            index += 1
        pairings.append((home, away))
    return pairings


def build_playoff_rounds(group_count: int):
    rounds = []
    current = _cross_group_pairings(group_count)
    while current:
        code, slug, name = _playoff_round_meta(len(current))
        rounds.append({"code": code, "slug": slug, "name": name, "pairings": current})
        if len(current) == 1:
            break
        current = _next_round_pairings(code, len(current))
    return rounds


def _append_dynamic_playoff(tournament: Tournament, group_count: int):
    for offset, round_def in enumerate(build_playoff_rounds(group_count), start=2):
        phase = TournamentPhase.objects.create(
            tournament=tournament,
            name=round_def["name"],
            slug=round_def["slug"],
            phase_type="knockout",
            order=offset,
            status="pending",
            config={"rounds": [round_def["code"]]},
        )
        bracket = Bracket.objects.create(phase=phase, name=round_def["name"])
        for position, (home, away) in enumerate(round_def["pairings"], start=1):
            BracketNode.objects.create(
                bracket=bracket,
                round=round_def["code"],
                position=position,
                home_source=home,
                away_source=away,
            )


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
