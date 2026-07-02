"""Lógica de line score por entradas para softbol/béisbol.

Convención: en la media entrada 'top' (alta) batea el visitante; en la
'bottom' (baja) batea el local. Los totales del partido se derivan siempre
de las entradas registradas.
"""

from django.db import transaction
from django.db.models import Sum

# Regla de nocaut (mercy rule) estándar de softbol: (entradas_completas, diferencia).
# Se evalúa de mayor a menor exigencia de entradas.
DEFAULT_MERCY_TIERS = [
    (4, 15),
    (5, 10),
]


def _half_totals(match):
    """Devuelve (carreras_local, carreras_visita) sumando las entradas."""
    rows = match.innings.values("half").annotate(total=Sum("runs"))
    top = bottom = 0
    for row in rows:
        if row["half"] == "top":
            top = row["total"] or 0
        else:
            bottom = row["total"] or 0
    # top = visitante batea, bottom = local batea
    return bottom, top


def recompute_match_from_innings(match, save=True):
    """Recalcula home_runs/away_runs (y espejo home_score/away_score) desde las entradas."""
    home_runs, away_runs = _half_totals(match)
    match.home_runs = home_runs
    match.away_runs = away_runs
    match.home_score = home_runs
    match.away_score = away_runs
    if save:
        match.save(
            update_fields=["home_runs", "away_runs", "home_score", "away_score"]
        )
    return home_runs, away_runs


def _completed_full_innings(match):
    """Número de entradas donde ambas medias están completas."""
    complete = (
        match.innings.filter(is_complete=True)
        .values("number", "half")
    )
    by_number = {}
    for row in complete:
        by_number.setdefault(row["number"], set()).add(row["half"])
    return sum(1 for halves in by_number.values() if {"top", "bottom"} <= halves)


def check_game_over(match):
    """Determina si el juego terminó según reglas de softbol.

    Retorna dict: {"over": bool, "reason": str|None, "winner": "home"|"away"|None}.
    Considera: regulación (N entradas), walk-off y mercy rule.
    """
    tournament = match.tournament
    regulation = tournament.regulation_innings or 7
    home_runs, away_runs = recompute_match_from_innings(match, save=False)

    result = {"over": False, "reason": None, "winner": None}

    def winner_side():
        if home_runs > away_runs:
            return "home"
        if away_runs > home_runs:
            return "away"
        return None

    # Última media entrada registrada
    last = match.innings.order_by("number", "-half").last()
    if last is None:
        return result

    completed = _completed_full_innings(match)

    # Mercy rule: al cerrar una entrada completa (o media alta con local arriba)
    if tournament.mercy_rule_enabled:
        diff = abs(home_runs - away_runs)
        for min_innings, min_diff in sorted(DEFAULT_MERCY_TIERS):
            if completed >= min_innings and diff >= min_diff and winner_side():
                result.update(
                    over=True,
                    reason=f"Nocaut ({min_diff}+ carreras tras {min_innings} entradas)",
                    winner=winner_side(),
                )
                return result

    # Walk-off: local se pone arriba bateando en la baja de entrada >= regulación
    if (
        last.half == "bottom"
        and last.number >= regulation
        and home_runs > away_runs
    ):
        result.update(over=True, reason="Walk-off", winner="home")
        return result

    # Fin de regulación
    if last.number >= regulation:
        # Tras la alta de la última entrada, si el local ya gana no batea
        if last.half == "top" and last.is_complete and home_runs > away_runs:
            result.update(over=True, reason="Fin de regulación", winner="home")
            return result
        # Baja completa y sin empate
        if last.half == "bottom" and last.is_complete and winner_side():
            result.update(over=True, reason="Fin de regulación", winner=winner_side())
            return result

    return result


@transaction.atomic
def upsert_inning(match, number, half, *, runs=None, hits=None, errors=None,
                  is_complete=None):
    """Crea o actualiza una media entrada y recalcula el marcador."""
    from sports.models import MatchInning

    inning, _ = MatchInning.objects.get_or_create(
        match=match, number=number, half=half
    )
    if runs is not None:
        inning.runs = max(0, int(runs))
    if hits is not None:
        inning.hits = max(0, int(hits))
    if errors is not None:
        inning.errors = max(0, int(errors))
    if is_complete is not None:
        inning.is_complete = bool(is_complete)
    inning.save()

    recompute_match_from_innings(match)
    return inning


def build_line_score(match):
    """Serializa el line score para el frontend: entradas + totales R/H/E."""
    innings = list(match.innings.all())
    by_key = {(i.number, i.half): i for i in innings}
    max_number = max((i.number for i in innings), default=0)

    home_line, away_line = [], []
    for n in range(1, max_number + 1):
        top = by_key.get((n, "top"))
        bottom = by_key.get((n, "bottom"))
        away_line.append(
            {
                "inning": n,
                "runs": top.runs if top else None,
                "played": top is not None,
            }
        )
        home_line.append(
            {
                "inning": n,
                "runs": bottom.runs if bottom else None,
                "played": bottom is not None,
            }
        )

    home_runs, away_runs = _half_totals(match)
    home_hits = sum(i.hits for i in innings if i.half == "bottom")
    away_hits = sum(i.hits for i in innings if i.half == "top")
    home_errors = sum(i.errors for i in innings if i.half == "bottom")
    away_errors = sum(i.errors for i in innings if i.half == "top")

    return {
        "innings_count": max_number,
        "home": {
            "line": home_line,
            "runs": home_runs,
            "hits": home_hits,
            "errors": home_errors,
        },
        "away": {
            "line": away_line,
            "runs": away_runs,
            "hits": away_hits,
            "errors": away_errors,
        },
    }
