"""Validación de alineaciones por deporte."""

SOFTBALL_FIELD_POSITIONS = frozenset(
    {
        "pitcher",
        "catcher",
        "first_base",
        "second_base",
        "third_base",
        "shortstop",
        "left_field",
        "center_field",
        "right_field",
    }
)

SOFTBALL_ALL_STARTER_POSITIONS = SOFTBALL_FIELD_POSITIONS | {"designated_hitter"}


def get_required_starters(sport_type: str, lineup_size: int = 9) -> tuple[int, int]:
    """Retorna (mínimo, máximo) titulares según deporte."""
    if sport_type == "football":
        return 6, 11
    if sport_type == "softball":
        size = 10 if lineup_size == 10 else 9
        return size, size
    return 1, 25


def validate_softball_lineup(players_data: list[dict], lineup_size: int = 9) -> list[str]:
    """Valida alineación de softbol. Retorna lista de errores."""
    errors: list[str] = []
    starters = [p for p in players_data if p.get("is_starter", True)]
    required = 10 if lineup_size == 10 else 9

    if len(starters) != required:
        errors.append(
            f"Debes alinear exactamente {required} titulares "
            f"({'9 en campo + bateador designado' if required == 10 else '9 en campo'})."
        )

    field_starters = [
        p for p in starters if p.get("position") in SOFTBALL_FIELD_POSITIONS
    ]
    if len(field_starters) != 9:
        errors.append("Debes cubrir las 9 posiciones defensivas (P, C, 1B, 2B, 3B, SS, LF, CF, RF).")

    field_positions = [p.get("position") for p in field_starters]
    if len(field_positions) != len(set(field_positions)):
        errors.append("Cada posición defensiva debe tener un solo jugador.")

    if lineup_size == 10:
        dh_count = sum(
            1 for p in starters if p.get("position") == "designated_hitter"
        )
        if dh_count != 1:
            errors.append(
                "Con alineación de 10 jugadores debes incluir un bateador designado (DH/EP)."
            )
    else:
        if any(p.get("position") == "designated_hitter" for p in starters):
            errors.append(
                "El bateador designado solo aplica cuando el torneo permite 10 titulares."
            )

    player_ids = [p.get("player") for p in starters]
    if len(player_ids) != len(set(player_ids)):
        errors.append("Un jugador no puede aparecer dos veces en la alineación.")

    orders = [p.get("batting_order") for p in starters if p.get("batting_order")]
    if orders and len(orders) != len(set(orders)):
        errors.append("El orden de bateo no puede repetir números.")

    return errors


def validate_lineup_for_sport(
    sport_type: str, players_data: list[dict], lineup_size: int = 9
) -> list[str]:
    if sport_type == "softball":
        return validate_softball_lineup(players_data, lineup_size)
    starters = [p for p in players_data if p.get("is_starter", True)]
    min_s, max_s = get_required_starters(sport_type, lineup_size)
    errors: list[str] = []
    if len(starters) < min_s:
        errors.append(f"Debes alinear al menos {min_s} titulares.")
    if len(starters) > max_s:
        errors.append(f"No puedes tener más de {max_s} titulares.")
    return errors
