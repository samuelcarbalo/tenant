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

        if (
            tournament.has_second_group_phase
            and phase.phase_type == "group_stage"
            and phase.order == 1
        ):
            rules = dict(phase.advancement_rules or {})
            rules["type"] = "top_n_per_group"
            rules["n"] = tournament.first_phase_qualified_per_group or 2
            phase.advancement_rules = rules
            phase.save(update_fields=["advancement_rules"])

    if template.get("dynamic_playoff"):
        if tournament.has_second_group_phase:
            _append_second_group_phase(tournament)
        else:
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


def build_rounds_from_pairings(pairings):
    rounds = []
    current = pairings
    while current:
        code, slug, name = _playoff_round_meta(len(current))
        rounds.append({"code": code, "slug": slug, "name": name, "pairings": current})
        if len(current) == 1:
            break
        current = _next_round_pairings(code, len(current))
    return rounds


def build_playoff_rounds(group_count: int):
    return build_rounds_from_pairings(_cross_group_pairings(group_count))


SECOND_PHASE_SLUG = "segunda-fase"


def _group_rank(slug: str, rank: int):
    return {"type": "group_rank", "group_slug": slug, "rank": rank}


def _second_phase_pairings(group_slugs, qualifiers: int):
    qualifiers = max(1, int(qualifiers or 1))
    if len(group_slugs) <= 1:
        slug = group_slugs[0]
        ranks = list(range(1, qualifiers + 1))
        pairings = []
        low, high = 0, len(ranks) - 1
        while low < high:
            pairings.append((_group_rank(slug, ranks[low]), _group_rank(slug, ranks[high])))
            low += 1
            high -= 1
        if low == high:
            pairings.append((_group_rank(slug, ranks[low]), {"type": "bye"}))
        return pairings
    home_slug, away_slug = group_slugs[0], group_slugs[1]
    return [
        (
            _group_rank(home_slug, rank),
            _group_rank(away_slug, qualifiers + 1 - rank),
        )
        for rank in range(1, qualifiers + 1)
    ]


def _append_playoff_rounds(tournament: Tournament, pairings, start_order: int):
    for offset, round_def in enumerate(build_rounds_from_pairings(pairings), start=start_order):
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


def _append_second_group_phase(tournament: Tournament):
    count = tournament.second_phase_groups_count or 2
    if count not in (1, 2):
        count = 2
    qualifiers_out = max(1, int(tournament.second_phase_qualified_per_group or 2))
    first_phase = (
        tournament.phases.filter(phase_type="group_stage").order_by("order").first()
    )
    first_groups = first_phase.groups.count() if first_phase else 0
    first_n = max(1, int(tournament.first_phase_qualified_per_group or 2))
    total_in = max(first_groups * first_n, count)
    cap = max(2, (total_in + count - 1) // count)
    phase = TournamentPhase.objects.create(
        tournament=tournament,
        name="Segunda fase de grupos",
        slug=SECOND_PHASE_SLUG,
        phase_type="group_stage",
        order=2,
        status="pending",
        config={"teams_per_group": cap, "stage": "second"},
        advancement_rules={"type": "top_n_per_group", "n": qualifiers_out},
    )
    slugs = []
    for i in range(count):
        letter = chr(ord("A") + i)
        slug = f"segunda-{letter.lower()}"
        slugs.append(slug)
        CompetitionGroup.objects.create(
            phase=phase,
            name=f"Grupo {letter}",
            slug=slug,
            order=i + 1,
            max_teams=cap,
        )
    _append_playoff_rounds(
        tournament,
        _second_phase_pairings(slugs, qualifiers_out),
        start_order=3,
    )


def _append_dynamic_playoff(tournament: Tournament, group_count: int):
    _append_playoff_rounds(
        tournament, _cross_group_pairings(group_count), start_order=2
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


def _first_phase_qualifiers(tournament: Tournament):
    from sports.scoring import StandingsService

    phase = (
        tournament.phases.filter(phase_type="group_stage")
        .exclude(slug=SECOND_PHASE_SLUG)
        .order_by("order")
        .first()
    )
    if not phase:
        return []
    per_group = max(1, int(tournament.first_phase_qualified_per_group or 2))
    selected = []
    seen = set()
    for group in phase.groups.order_by("order"):
        rows = StandingsService.compute(tournament, phase=phase, group=group)
        taken = 0
        for row in rows:
            team = row["team"]
            if team.id in seen:
                continue
            selected.append(
                {
                    "team": team,
                    "from_group": group.name,
                    "rank": row["position"],
                }
            )
            seen.add(team.id)
            taken += 1
            if taken >= per_group:
                break
    return selected


def _second_phase(tournament: Tournament):
    if not tournament.has_second_group_phase:
        raise ValueError("Este torneo no incluye una segunda fase de grupos.")
    phase = tournament.phases.filter(slug=SECOND_PHASE_SLUG).first()
    if not phase:
        raise ValueError("La segunda fase de grupos no está creada.")
    return phase


def second_phase_preview(tournament: Tournament):
    phase = _second_phase(tournament)
    qualifiers = _first_phase_qualifiers(tournament)
    return {
        "assignment_method": tournament.second_phase_assignment_method or "RANDOM",
        "qualifiers": [
            {
                "team_id": str(item["team"].id),
                "team_name": item["team"].name,
                "from_group": item["from_group"],
                "rank": item["rank"],
            }
            for item in qualifiers
        ],
        "groups": [
            {
                "id": str(group.id),
                "slug": group.slug,
                "name": group.name,
                "team_ids": [
                    str(team_id)
                    for team_id in group.memberships.order_by("seed").values_list(
                        "team_id", flat=True
                    )
                ],
            }
            for group in phase.groups.order_by("order")
        ],
    }


def _snake_assign(groups, qualifiers):
    buckets = {group.id: [] for group in groups}
    if not groups:
        return []
    index = 0
    direction = 1
    for item in qualifiers:
        buckets[groups[index].id].append(item["team"])
        if len(groups) == 1:
            continue
        nxt = index + direction
        if nxt < 0 or nxt >= len(groups):
            direction *= -1
        else:
            index = nxt
    return [(group, buckets[group.id]) for group in groups]


def _manual_assign(groups, qualifiers, payload_groups):
    if not payload_groups:
        raise ValueError("Envía la lista de equipos de cada grupo de la segunda fase.")
    by_slug = {group.slug: group for group in groups}
    by_id = {str(item["team"].id): item["team"] for item in qualifiers}
    buckets = {group.id: [] for group in groups}
    seen = set()
    for entry in payload_groups:
        slug = entry.get("slug")
        group = by_slug.get(slug)
        if not group:
            raise ValueError(f"Grupo desconocido: {slug}")
        for raw in entry.get("team_ids") or []:
            key = str(raw)
            team = by_id.get(key)
            if team is None:
                raise ValueError("Hay equipos que no clasificaron en la primera fase.")
            if key in seen:
                raise ValueError("Un equipo no puede estar en dos grupos.")
            seen.add(key)
            buckets[group.id].append(team)
    missing = [
        item["team"].name
        for item in qualifiers
        if str(item["team"].id) not in seen
    ]
    if missing:
        raise ValueError("Faltan clasificados por asignar: " + ", ".join(missing))
    empty = [group.name for group in groups if not buckets[group.id]]
    if empty:
        raise ValueError("Cada grupo de la segunda fase debe tener al menos un equipo.")
    return [(group, buckets[group.id]) for group in groups]


def generate_second_group_phase(tournament: Tournament, payload=None):
    """Reparte los clasificados de la primera fase en los grupos de la segunda."""
    payload = payload or {}
    phase = _second_phase(tournament)
    if Match.objects.filter(phase=phase).exists():
        raise ValueError("La segunda fase ya tiene partidos. No se puede redistribuir.")
    qualifiers = _first_phase_qualifiers(tournament)
    if len(qualifiers) < 2:
        raise ValueError(
            "Se necesitan al menos 2 clasificados de la primera fase. "
            "Asigna equipos a esos grupos antes de generar la segunda."
        )
    groups = list(phase.groups.order_by("order"))
    method = (tournament.second_phase_assignment_method or "RANDOM").upper()
    if method == "MANUAL":
        assignment = _manual_assign(groups, qualifiers, payload.get("groups") or [])
    else:
        assignment = _snake_assign(groups, qualifiers)
    for group, teams in assignment:
        if len(teams) > group.max_teams:
            group.max_teams = len(teams)
            group.save(update_fields=["max_teams"])
        assign_teams_to_group(group, [team.id for team in teams])
    return phase


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
