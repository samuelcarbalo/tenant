"""Encabezados exactos esperados por módulo de importación."""

IMPORT_MODULES = (
    "schedule",
    "players",
    "jobs",
    "products",
    "discounts",
)

TEMPLATE_HEADERS: dict[str, list[str]] = {
    "schedule": [
        "tournament_slug",
        "home_team",
        "away_team",
        "match_date",
        "venue",
        "round_number",
        "match_week",
        "phase",
        "status",
        "notes",
    ],
    "players": [
        "tournament_slug",
        "team_name",
        "first_name",
        "last_name",
        "id_number",
        "email",
        "jersey_number",
        "position",
        "birth_date",
        "is_captain",
    ],
    "jobs": [
        "title",
        "company_name",
        "description",
        "requirements",
        "location",
        "remote",
        "category",
        "job_type",
        "salary_min",
        "salary_max",
        "expires_at",
        "is_external",
        "external_apply_url",
    ],
    "products": [
        "name",
        "sku",
        "description",
        "short_description",
        "category",
        "subcategory",
        "price_cop",
        "compare_at_price_cop",
        "stock",
        "image_url",
        "is_featured",
        "is_published",
    ],
    "discounts": [
        "name",
        "product_sku",
        "product_id",
        "discount_type",
        "discount_percentage",
        "discount_amount_cop",
        "discount_price",
        "start_date",
        "end_date",
        "is_flash_sale",
        "is_active",
    ],
}

TEMPLATE_SIGNATURES: dict[str, tuple[str, ...]] = {
    "schedule": ("tournament_slug", "home_team", "away_team"),
    "players": ("team_name", "first_name", "last_name"),
    "jobs": ("title", "company_name"),
    "products": ("name", "sku", "price_cop"),
    "discounts": ("discount_type", "start_date", "end_date"),
}

WRONG_TEMPLATE_MESSAGE = "La plantilla subida no corresponde a la categoría seleccionada."


def headers_match_module(received: list[str], module: str) -> bool:
    present = {str(h).strip() for h in received if h is not None and str(h).strip()}
    keys = TEMPLATE_SIGNATURES.get(module) or tuple(TEMPLATE_HEADERS.get(module, [])[:2])
    return all(key in present for key in keys)
