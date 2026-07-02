"""Planes de publicidad pagados con créditos."""

from datetime import timedelta

SPONSORSHIP_PLANS = {
    "week": {
        "id": "week",
        "label": "Semana",
        "credits": 80,
        "days": 7,
        "description": "Patrocinio exclusivo del torneo por 7 días.",
    },
    "month": {
        "id": "month",
        "label": "Mes",
        "credits": 250,
        "days": 30,
        "description": "Patrocinio exclusivo del torneo por 30 días.",
    },
    "bimester": {
        "id": "bimester",
        "label": "Bimestre",
        "credits": 450,
        "days": 60,
        "description": (
            "Patrocinio exclusivo por 60 días. Al vencer el plazo el espacio "
            "queda disponible para un nuevo anunciante, aunque el torneo siga activo."
        ),
    },
}

TOURNAMENT_SPONSORSHIP_POSITIONS = [
    "tournament_detail",
    "standings_top",
    "standings_bottom",
    "match_detail",
]

CLASSIFIED_AD_PLANS = {
    "basic": {
        "id": "basic",
        "label": "Básico",
        "credits": 15,
        "target_reach": 50,
        "frequency_cap": 3,
        "days": 15,
        "description": "Hasta 50 personas distintas, máx. 3 veces por persona.",
    },
    "standard": {
        "id": "standard",
        "label": "Estándar",
        "credits": 25,
        "target_reach": 100,
        "frequency_cap": 5,
        "days": 30,
        "description": "Hasta 100 personas distintas, máx. 5 veces por persona.",
    },
    "plus": {
        "id": "plus",
        "label": "Plus",
        "credits": 45,
        "target_reach": 250,
        "frequency_cap": 5,
        "days": 30,
        "description": "Hasta 250 personas distintas, máx. 5 veces por persona.",
    },
}

CLASSIFIED_POSITIONS = {
    "job": [
        ("jobs_list_top", "Listado de empleos — arriba"),
        ("job_detail", "Detalle de empleo"),
    ],
    "real_estate": [
        ("listings_list_top", "Listado inmobiliario — arriba"),
        ("listing_detail", "Detalle de propiedad"),
    ],
    "event": [
        ("events_list_top", "Listado de eventos — arriba"),
        ("event_detail", "Detalle de evento"),
    ],
}

CREDIT_COST_EVENT = 5


def get_sponsorship_plan(plan_id: str) -> dict | None:
    return SPONSORSHIP_PLANS.get(plan_id)


def get_classified_plan(plan_id: str) -> dict | None:
    return CLASSIFIED_AD_PLANS.get(plan_id)


def sponsorship_end_date(start_date, plan_id: str):
    plan = get_sponsorship_plan(plan_id)
    if not plan:
        return start_date
    return start_date + timedelta(days=plan["days"])
