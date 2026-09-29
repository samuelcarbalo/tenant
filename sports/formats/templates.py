"""Plantillas de formato de torneo."""

FORMAT_TEMPLATES = {
    "legacy_league": {
        "id": "legacy_league",
        "label": "Liga simple",
        "description": "Liga simple: un solo grupo general. Todos los equipos juegan entre sí y hay una única tabla. No se divide en Grupo A, Grupo B ni hay eliminatoria.",
        "sport_types": ["football", "softball", "basketball", "volleyball", "tennis", "other"],
        "structure_mode": "legacy",
        "grouping": "single_table",
        "allows_group_count": False,
        "phases": [],
    },
    "single_day_quadrangular": {
        "id": "single_day_quadrangular",
        "label": "Cuadrangular (1 día)",
        "description": "Un solo grupo de 4 equipos, todos contra todos en un día. No se crean grupos adicionales.",
        "sport_types": ["softball", "football", "basketball", "volleyball"],
        "structure_mode": "structured",
        "grouping": "fixed_group",
        "allows_group_count": False,
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
        "label": "Varios grupos (sin playoffs)",
        "description": "Primera fase dividida en grupos de 4 (A, B, C…). Cada grupo juega todos contra todos y tiene su tabla. No hay fase eliminatoria. El calendario solo enfrenta equipos del mismo grupo.",
        "sport_types": ["softball", "football"],
        "structure_mode": "structured",
        "grouping": "multi_group",
        "allows_group_count": True,
        "teams_per_group": 4,
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
        "description": "Liga simple en una fase: un solo grupo general y una tabla única. No se divide en Grupo A, Grupo B ni hay eliminatoria.",
        "sport_types": ["football", "softball", "basketball", "volleyball"],
        "structure_mode": "structured",
        "grouping": "single_table",
        "allows_group_count": False,
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
        "description": "Un solo grupo de 4. Todos contra todos y luego final entre los 2 primeros. No admite varios grupos.",
        "sport_types": ["softball", "football"],
        "structure_mode": "structured",
        "grouping": "fixed_group",
        "allows_group_count": False,
        "qualifiers_per_group": 2,
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
        "label": "Fase de grupos + playoffs",
        "description": "Elige cuántos grupos de 4 quieres (A, B, C…). Clasifican 2 por grupo. La eliminatoria se arma según esa cantidad: el 1.º de un grupo enfrenta al 2.º del siguiente, y luego se juega hasta la final.",
        "sport_types": ["softball", "football"],
        "structure_mode": "structured",
        "grouping": "multi_group",
        "allows_group_count": True,
        "teams_per_group": 4,
        "qualifiers_per_group": 2,
        "dynamic_playoff": True,
        "phases": [
            {
                "name": "Fase de grupos",
                "slug": "cuadrangulares",
                "phase_type": "group_stage",
                "order": 1,
                "config": {"teams_per_group": 4},
                "groups_auto": True,
                "advancement_rules": {"type": "top_n_per_group", "n": 2},
            },
        ],
    },
    "round_robin_knockout_8": {
        "id": "round_robin_knockout_8",
        "label": "Todos contra todos (8) + Semis + Final",
        "description": "8 equipos en una sola tabla. Los 4 primeros de esa tabla única pasan a semifinales. No hay Grupo A ni Grupo B.",
        "sport_types": ["softball", "football", "basketball", "volleyball"],
        "structure_mode": "structured",
        "grouping": "single_table",
        "allows_group_count": False,
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
    "knockout_direct_8": {
        "id": "knockout_direct_8",
        "label": "Eliminación directa (8 equipos)",
        "description": "Cuadro de 8: cuartos, semifinales y final. Sin fase de grupos ni todos contra todos.",
        "sport_types": ["football", "softball", "basketball", "volleyball"],
        "structure_mode": "structured",
        "grouping": "knockout",
        "allows_group_count": False,
        "default_max_teams": 8,
        "phases": [
            {
                "name": "Cuartos de final",
                "slug": "cuartos",
                "phase_type": "knockout",
                "order": 1,
                "config": {"rounds": ["quarterfinal"]},
                "bracket": {
                    "name": "Cuartos",
                    "nodes": [
                        {
                            "round": "quarterfinal",
                            "position": 1,
                            "home_source": {"type": "seed", "rank": 1},
                            "away_source": {"type": "seed", "rank": 8},
                        },
                        {
                            "round": "quarterfinal",
                            "position": 2,
                            "home_source": {"type": "seed", "rank": 4},
                            "away_source": {"type": "seed", "rank": 5},
                        },
                        {
                            "round": "quarterfinal",
                            "position": 3,
                            "home_source": {"type": "seed", "rank": 2},
                            "away_source": {"type": "seed", "rank": 7},
                        },
                        {
                            "round": "quarterfinal",
                            "position": 4,
                            "home_source": {"type": "seed", "rank": 3},
                            "away_source": {"type": "seed", "rank": 6},
                        },
                    ],
                },
            },
            {
                "name": "Semifinales",
                "slug": "semifinales",
                "phase_type": "knockout",
                "order": 2,
                "config": {"rounds": ["semifinal"]},
                "bracket": {
                    "name": "Semifinales",
                    "nodes": [
                        {
                            "round": "semifinal",
                            "position": 1,
                            "home_source": {
                                "type": "bracket_winner",
                                "round": "quarterfinal",
                                "position": 1,
                            },
                            "away_source": {
                                "type": "bracket_winner",
                                "round": "quarterfinal",
                                "position": 2,
                            },
                        },
                        {
                            "round": "semifinal",
                            "position": 2,
                            "home_source": {
                                "type": "bracket_winner",
                                "round": "quarterfinal",
                                "position": 3,
                            },
                            "away_source": {
                                "type": "bracket_winner",
                                "round": "quarterfinal",
                                "position": 4,
                            },
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
                            "home_source": {
                                "type": "bracket_winner",
                                "round": "semifinal",
                                "position": 1,
                            },
                            "away_source": {
                                "type": "bracket_winner",
                                "round": "semifinal",
                                "position": 2,
                            },
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
