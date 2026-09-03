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
        "badge": "Paquete intermedio",
        "savings_cop": 5000,
        "description": "50 créditos para empleos, inmuebles o eventos. El Módulo Deportivo cuesta 200 créditos / 30 días.",
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
    "platino": {
        "id": "platino",
        "name": "Paquete Platino",
        "credits": 250,
        "price_cop": 200000,
        "badge": "Patrocinio mensual",
        "savings_cop": 50000,
        "description": (
            "250 créditos — suficientes para activar 1 mes ilimitado de Tienda Virtual "
            "al publicar tu primer producto, o usar en torneos y demás servicios."
        ),
    },
    "diamante": {
        "id": "diamante",
        "name": "Paquete Diamante",
        "credits": 450,
        "price_cop": 350000,
        "badge": "Patrocinio ejecutivo",
        "savings_cop": 100000,
        "description": (
            "450 créditos: al publicar en tienda con saldo ≥ 250 se activan 30 días ilimitados "
            "(250 créditos); los 200 restantes quedan libres para empleos, inmuebles, torneos "
            "y demás servicios."
        ),
    },
}

# Costos internos de consumo
CREDIT_COST_JOB = 5
CREDIT_COST_REAL_ESTATE = 5
CREDIT_COST_TOURNAMENT = 200
CREDIT_COST_SPORTS_MODULE = 200
SPORTS_MODULE_DAYS = 30
CREDIT_COST_EVENT = 5
CREDIT_COST_STORE = 10
CREDIT_COST_STORE_UNLIMITED = 250
STORE_UNLIMITED_DAYS = 30
CREDIT_VALUE_COP = 1000  # 1 crédito = $1.000 COP


def get_package(package_id: str) -> dict | None:
    return CREDIT_PACKAGES.get(package_id)
