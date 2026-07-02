"""Plantillas de formato de torneo."""

FORMAT_TEMPLATES = {
    "legacy_league": {
        "id": "legacy_league",
        "label": "Liga simple",
        "description": "Todos contra todos en una sola tabla.",
        "sport_types": ["football", "softball", "basketball", "volleyball", "tennis", "other"],
        "structure_mode": "legacy",
        "phases": [],
    },
    "single_day_quadrangular": {
        "id": "single_day_quadrangular",
        "label": "Cuadrangular (1 día)",
        "description": "4 equipos, todos contra todos en un solo día.",
        "sport_types": ["softball", "football", "basketball", "volleyball"],
        "structure_mode": "structured",
        "default_max_teams": 4,
        "phases": [
            {
                "name": "Cuadrangular",
                "slug": "cuadrangular",
                "phase_type": "round_robin",
                "order": 1,
                "config": {"single_day": True, "teams_per_group": 4},
                "groups": [{"name": "Cuadrangular", "slug": "cuadrangular", "max_teams": 4}],
            }
        ],
    },
    "multi_quadrangular": {
        "id": "multi_quadrangular",
        "label": "Varios cuadrangulares",
        "description": "Grupos de 4 equipos con tabla independiente por cuadrangular.",
        "sport_types": ["softball", "football"],
        "structure_mode": "structured",
        "phases": [
            {
                "name": "Cuadrangulares",
                "slug": "cuadrangulares",
                "phase_type": "group_stage",
                "order": 1,
                "config": {"teams_per_group": 4},
                "groups_auto": True,
            }
        ],
    },
    "round_robin_single": {
        "id": "round_robin_single",
        "label": "Todos contra todos",
        "description": "Una fase regular con tabla única.",
        "sport_types": ["football", "softball", "basketball", "volleyball"],
        "structure_mode": "structured",
        "phases": [
            {
                "name": "Fase regular",
                "slug": "regular",
                "phase_type": "round_robin",
                "order": 1,
                "config": {},
                "groups": [],
            }
        ],
    },
    "single_quadrangular_final": {
        "id": "single_quadrangular_final",
        "label": "Cuadrangular + Final",
        "description": "4 equipos en cuadrangular; juegan final los 2 primeros.",
        "sport_types": ["softball", "football"],
        "structure_mode": "structured",
        "default_max_teams": 4,
        "phases": [
            {
                "name": "Cuadrangular",
                "slug": "cuadrangular",
                "phase_type": "round_robin",
                "order": 1,
                "config": {"single_day": True, "teams_per_group": 4},
                "groups": [{"name": "Cuadrangular", "slug": "cuadrangular", "max_teams": 4}],
                "advancement_rules": {"type": "top_n_per_group", "n": 2},
            },
            {
                "name": "Final",
                "slug": "final",
                "phase_type": "knockout",
                "order": 2,
                "config": {"rounds": ["final"]},
                "bracket": {
                    "name": "Final",
                    "nodes": [
                        {
                            "round": "final",
                            "position": 1,
                            "home_source": {"type": "group_rank", "group_slug": "cuadrangular", "rank": 1},
                            "away_source": {"type": "group_rank", "group_slug": "cuadrangular", "rank": 2},
                        }
                    ],
                },
            },
        ],
    },
    "multi_quadrangular_knockout": {
        "id": "multi_quadrangular_knockout",
        "label": "Cuadrangulares + Semis + Final",
        "description": "2+ cuadrangulares; pasan 2 por grupo a semifinales y final.",
        "sport_types": ["softball", "football"],
        "structure_mode": "structured",
        "default_max_teams": 8,
        "phases": [
            {
                "name": "Cuadrangulares",
                "slug": "cuadrangulares",
                "phase_type": "group_stage",
                "order": 1,
                "config": {"teams_per_group": 4},
                "groups_auto": True,
                "advancement_rules": {"type": "top_n_per_group", "n": 2},
            },
            {
                "name": "Semifinales",
                "slug": "semifinales",
                "phase_type": "knockout",
                "order": 2,
                "config": {"rounds": ["semifinal"], "seeding": "cross_group"},
                "bracket": {
                    "name": "Semifinales",
                    "nodes": [
                        {
                            "round": "semifinal",
                            "position": 1,
                            "home_source": {"type": "group_rank", "group_slug": "cuadrangular-a", "rank": 1},
                            "away_source": {"type": "group_rank", "group_slug": "cuadrangular-b", "rank": 2},
                        },
                        {
                            "round": "semifinal",
                            "position": 2,
                            "home_source": {"type": "group_rank", "group_slug": "cuadrangular-b", "rank": 1},
                            "away_source": {"type": "group_rank", "group_slug": "cuadrangular-a", "rank": 2},
                        },
                    ],
                },
            },
            {
                "name": "Final",
                "slug": "final",
                "phase_type": "knockout",
                "order": 3,
                "config": {"rounds": ["final"]},
                "bracket": {
                    "name": "Final",
                    "nodes": [
                        {
                            "round": "final",
                            "position": 1,
                            "home_source": {"type": "bracket_winner", "round": "semifinal", "position": 1},
                            "away_source": {"type": "bracket_winner", "round": "semifinal", "position": 2},
                        }
                    ],
                },
            },
        ],
    },
    "round_robin_knockout_8": {
        "id": "round_robin_knockout_8",
        "label": "Todos contra todos (8) + Semis + Final",
        "description": "8 equipos en fase regular; top 4 a semifinales.",
        "sport_types": ["softball", "football", "basketball", "volleyball"],
        "structure_mode": "structured",
        "default_max_teams": 8,
        "phases": [
            {
                "name": "Fase regular",
                "slug": "regular",
                "phase_type": "round_robin",
                "order": 1,
                "config": {},
                "groups": [],
                "advancement_rules": {"type": "top_n_overall", "n": 4},
            },
            {
                "name": "Semifinales",
                "slug": "semifinales",
                "phase_type": "knockout",
                "order": 2,
                "bracket": {
                    "name": "Semifinales",
                    "nodes": [
                        {
                            "round": "semifinal",
                            "position": 1,
                            "home_source": {"type": "overall_rank", "phase_slug": "regular", "rank": 1},
                            "away_source": {"type": "overall_rank", "phase_slug": "regular", "rank": 4},
                        },
                        {
                            "round": "semifinal",
                            "position": 2,
                            "home_source": {"type": "overall_rank", "phase_slug": "regular", "rank": 2},
                            "away_source": {"type": "overall_rank", "phase_slug": "regular", "rank": 3},
                        },
                    ],
                },
            },
            {
                "name": "Final",
                "slug": "final",
                "phase_type": "knockout",
                "order": 3,
                "bracket": {
                    "name": "Final",
                    "nodes": [
                        {
                            "round": "final",
                            "position": 1,
                            "home_source": {"type": "bracket_winner", "round": "semifinal", "position": 1},
                            "away_source": {"type": "bracket_winner", "round": "semifinal", "position": 2},
                        }
                    ],
                },
            },
        ],
    },
}


def get_template(template_id):
    return FORMAT_TEMPLATES.get(template_id)


def list_templates(sport_type=None):
    templates = list(FORMAT_TEMPLATES.values())
    if sport_type:
        templates = [t for t in templates if sport_type in t.get("sport_types", [])]
    return templates
