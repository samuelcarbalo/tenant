from copy import deepcopy

from .registry import SCORING_DEFAULTS


def get_scoring_config(tournament):
    """Configuración de marcador para un torneo (defaults + overrides)."""
    sport = getattr(tournament, "sport_type", "football") or "football"
    base = deepcopy(SCORING_DEFAULTS.get(sport, SCORING_DEFAULTS["other"]))
    overrides = getattr(tournament, "scoring_config", None) or {}
    if overrides:
        for key, value in overrides.items():
            if key == "points" and isinstance(value, dict):
                base["points"].update(value)
            else:
                base[key] = value
    return base
