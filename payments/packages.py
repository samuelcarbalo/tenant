"""Paquetes de créditos disponibles para compra."""

CREDIT_PACKAGES = {
    "basico": {
        "id": "basico",
        "name": "Paquete Básico",
        "credits": 20,
        "price_cop": 20000,
        "badge": None,
        "savings_cop": 0,
        "description": "Precio estándar — ideal para probar la plataforma.",
    },
    "bronce": {
        "id": "bronce",
        "name": "Paquete Bronce",
        "credits": 30,
        "price_cop": 28000,
        "badge": "Promoción",
        "savings_cop": 2000,
        "description": "Ahorra $2.000 COP respecto al precio estándar.",
    },
    "plata": {
        "id": "plata",
        "name": "Paquete Plata",
        "credits": 50,
        "price_cop": 45000,
        "badge": "¡Ideal para 1 Torneo!",
        "savings_cop": 5000,
        "description": "50 créditos — suficiente para crear un torneo de fútbol.",
    },
    "oro": {
        "id": "oro",
        "name": "Paquete Oro",
        "credits": 100,
        "price_cop": 80000,
        "badge": "¡Recomendado para Empresas!",
        "savings_cop": 20000,
        "description": "Máximo ahorro para empresas con publicaciones frecuentes.",
    },
}

# Costos internos de consumo
CREDIT_COST_JOB = 5
CREDIT_COST_REAL_ESTATE = 5
CREDIT_COST_TOURNAMENT = 50
CREDIT_COST_EVENT = 5
CREDIT_VALUE_COP = 1000  # 1 crédito = $1.000 COP


def get_package(package_id: str) -> dict | None:
    return CREDIT_PACKAGES.get(package_id)
