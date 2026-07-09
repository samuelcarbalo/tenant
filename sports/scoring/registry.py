"""Reglas de marcador y desempate por deporte."""

SCORING_DEFAULTS = {
    "football": {
        "primary_fields": ("home_score", "away_score"),
        "stat_for": "goals_for",
        "stat_against": "goals_against",
        "allows_draw": True,
        "points": {"win": 3, "draw": 1, "loss": 0},
        "tiebreakers": [
            "points",
            "goal_difference",
            "goals_for",
            "head_to_head",
            "name",
        ],
    },
    "softball": {
        "primary_fields": ("home_runs", "away_runs"),
        "stat_for": "runs",
        "stat_against": "runs_against",
        "allows_draw": False,
        "points": {"win": 2, "loss": 0},
        "tiebreakers": ["points", "wins", "average", "runs_for", "head_to_head", "name"],
    },
    "basketball": {
        "primary_fields": ("home_score", "away_score"),
        "stat_for": "goals_for",
        "stat_against": "goals_against",
        "allows_draw": False,
        "points": {"win": 2, "loss": 0},
        "tiebreakers": ["points", "wins", "goal_difference", "goals_for", "name"],
    },
    "volleyball": {
        "primary_fields": ("home_score", "away_score"),
        "stat_for": "goals_for",
        "stat_against": "goals_against",
        "allows_draw": False,
        "points": {"win": 2, "loss": 0},
        "tiebreakers": ["points", "wins", "goal_difference", "goals_for", "name"],
    },
    "tennis": {
        "primary_fields": ("home_score", "away_score"),
        "stat_for": "goals_for",
        "stat_against": "goals_against",
        "allows_draw": False,
        "points": {"win": 2, "loss": 0},
        "tiebreakers": ["points", "wins", "name"],
    },
    "other": {
        "primary_fields": ("home_score", "away_score"),
        "stat_for": "goals_for",
        "stat_against": "goals_against",
        "allows_draw": True,
        "points": {"win": 3, "draw": 1, "loss": 0},
        "tiebreakers": ["points", "goal_difference", "goals_for", "name"],
    },
}
