"""Lógica de importación por módulo."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import slugify

from .workbook import cell_bool, cell_str


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    text = str(value).strip()
    dt = parse_datetime(text)
    if dt is None:
        d = parse_date(text)
        if d is not None:
            dt = datetime(d.year, d.month, d.day)
    if dt is None:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _unique_product_slug(org, base: str) -> str:
    from ecommerce.models import Product

    slug = slugify(base)[:200] or "producto"
    candidate = slug
    n = 1
    while Product.objects.filter(organization=org, slug=candidate).exists():
        candidate = f"{slug}-{n}"[:220]
        n += 1
    return candidate


class ImportResult:
    def __init__(self):
        self.created = 0
        self.updated = 0
        self.errors: list[dict[str, Any]] = []

    def add_error(self, row: int, message: str, field: str | None = None):
        self.errors.append({"row": row, "field": field, "message": message})

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "error_count": len(self.errors),
            "errors": self.errors[:200],
        }


def import_schedule(*, rows: list[dict], organization, user) -> ImportResult:
    from sports.models import Match, Team, Tournament

    result = ImportResult()
    for row in rows:
        r = int(row.get("_row") or 0)
        t_slug = cell_str(row, "tournament_slug")
        home = cell_str(row, "home_team")
        away = cell_str(row, "away_team")
        match_date = _parse_dt(row.get("match_date"))
        if not t_slug or not home or not away or not match_date:
            result.add_error(r, "tournament_slug, home_team, away_team y match_date son obligatorios")
            continue
        tournament = Tournament.objects.filter(
            organization=organization, slug=t_slug
        ).first()
        if not tournament:
            tournament = Tournament.objects.filter(slug=t_slug).first()
        if not tournament:
            result.add_error(r, f"Torneo no encontrado: {t_slug}", "tournament_slug")
            continue
        home_team = Team.objects.filter(tournament=tournament, name__iexact=home).first()
        away_team = Team.objects.filter(tournament=tournament, name__iexact=away).first()
        if not home_team or not away_team:
            result.add_error(r, "Equipo local o visitante no encontrado en el torneo")
            continue
        status = cell_str(row, "status") or "scheduled"
        try:
            Match.objects.create(
                tournament=tournament,
                posted_by=user,
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
                venue=cell_str(row, "venue"),
                round_number=int(cell_str(row, "round_number") or 1),
                match_week=int(cell_str(row, "match_week") or 1),
                status=status,
                notes=cell_str(row, "notes"),
                match_type=(
                    cell_str(row, "phase")
                    if cell_str(row, "phase")
                    in {"group", "knockout", "friendly", "legacy"}
                    else "legacy"
                ),
            )
            result.created += 1
        except Exception as exc:  # noqa: BLE001
            result.add_error(r, str(exc))
    return result


def import_players(*, rows: list[dict], organization, user) -> ImportResult:
    from sports.models import Player, Team, Tournament

    result = ImportResult()
    for row in rows:
        r = int(row.get("_row") or 0)
        t_slug = cell_str(row, "tournament_slug")
        team_name = cell_str(row, "team_name")
        first = cell_str(row, "first_name")
        last = cell_str(row, "last_name")
        if not t_slug or not team_name or not first or not last:
            result.add_error(
                r, "tournament_slug, team_name, first_name y last_name son obligatorios"
            )
            continue
        tournament = Tournament.objects.filter(
            organization=organization, slug=t_slug
        ).first() or Tournament.objects.filter(slug=t_slug).first()
        if not tournament:
            result.add_error(r, f"Torneo no encontrado: {t_slug}", "tournament_slug")
            continue
        team = Team.objects.filter(tournament=tournament, name__iexact=team_name).first()
        if not team:
            result.add_error(r, f"Equipo no encontrado: {team_name}", "team_name")
            continue
        birth = None
        bd = row.get("birth_date")
        if bd:
            birth = parse_date(str(bd)) if not hasattr(bd, "year") else bd
            if isinstance(birth, datetime):
                birth = birth.date()
        jersey = cell_str(row, "jersey_number")
        try:
            Player.objects.create(
                first_name=first,
                last_name=last,
                id_number=cell_str(row, "id_number"),
                email=cell_str(row, "email"),
                posted_by=user,
                team=team,
                tournament=tournament,
                birth_date=birth,
                position=cell_str(row, "position") or "midfielder",
                jersey_number=int(jersey) if jersey.isdigit() else None,
                is_captain=cell_bool(row, "is_captain"),
            )
            result.created += 1
        except Exception as exc:  # noqa: BLE001
            result.add_error(r, str(exc))
    return result


def import_jobs(*, rows: list[dict], organization, user) -> ImportResult:
    from jobs.models import JobOffer

    result = ImportResult()
    for row in rows:
        r = int(row.get("_row") or 0)
        title = cell_str(row, "title")
        company = cell_str(row, "company_name")
        description = cell_str(row, "description")
        if not title or not company or not description:
            result.add_error(r, "title, company_name y description son obligatorios")
            continue
        expires = _parse_dt(row.get("expires_at"))
        if expires is None:
            from datetime import timedelta

            expires = timezone.now() + timedelta(days=30)
        try:
            JobOffer.objects.create(
                organization=organization,
                posted_by=user,
                title=title,
                company_name=company,
                description=description,
                requirements=cell_str(row, "requirements"),
                location=cell_str(row, "location"),
                remote=cell_bool(row, "remote"),
                category=cell_str(row, "category"),
                job_type=cell_str(row, "job_type") or "full_time",
                salary_min=_parse_decimal(row.get("salary_min")),
                salary_max=_parse_decimal(row.get("salary_max")),
                expires_at=expires,
                is_active=True,
            )
            result.created += 1
        except Exception as exc:  # noqa: BLE001
            result.add_error(r, str(exc))
    return result


def import_products(*, rows: list[dict], organization, user) -> ImportResult:
    from ecommerce.models import Category, Product, SubCategory

    result = ImportResult()
    for row in rows:
        r = int(row.get("_row") or 0)
        name = cell_str(row, "name")
        price = _parse_decimal(row.get("price_cop"))
        if not name or price is None:
            result.add_error(r, "name y price_cop son obligatorios")
            continue

        cat_name = cell_str(row, "category")
        sub_name = cell_str(row, "subcategory")
        category = None
        subcategory = None
        if cat_name:
            category, _ = Category.objects.get_or_create(
                organization=organization,
                slug=slugify(cat_name)[:140] or "general",
                defaults={"name": cat_name},
            )
            if category.name != cat_name:
                category.name = cat_name
                category.save(update_fields=["name", "updated_at"])
        if category and sub_name:
            subcategory, _ = SubCategory.objects.get_or_create(
                organization=organization,
                category=category,
                slug=slugify(sub_name)[:140] or "sub",
                defaults={"name": sub_name},
            )

        sku = cell_str(row, "sku")
        existing = None
        if sku:
            existing = Product.objects.filter(organization=organization, sku=sku).first()

        stock_raw = cell_str(row, "stock")
        stock = int(stock_raw) if stock_raw.isdigit() else 0
        payload = {
            "name": name,
            "description": cell_str(row, "description"),
            "short_description": cell_str(row, "short_description")[:300],
            "sku": sku,
            "price_cop": price,
            "compare_at_price_cop": _parse_decimal(row.get("compare_at_price_cop")),
            "stock": stock,
            "image_url": cell_str(row, "image_url"),
            "is_featured": cell_bool(row, "is_featured"),
            "is_published": cell_bool(row, "is_published", default=True),
            "category": category,
            "subcategory": subcategory,
        }
        try:
            with transaction.atomic():
                if existing:
                    for k, v in payload.items():
                        setattr(existing, k, v)
                    existing.save()
                    result.updated += 1
                else:
                    Product.objects.create(
                        organization=organization,
                        slug=_unique_product_slug(organization, name),
                        **payload,
                    )
                    result.created += 1
        except Exception as exc:  # noqa: BLE001
            result.add_error(r, str(exc))
    return result


def import_discounts(*, rows: list[dict], organization, user) -> ImportResult:
    from ecommerce.models import Product, ProductDiscount

    result = ImportResult()
    for row in rows:
        r = int(row.get("_row") or 0)
        name = cell_str(row, "name")
        start = _parse_dt(row.get("start_date"))
        end = _parse_dt(row.get("end_date"))
        if not name or not start or not end:
            result.add_error(r, "name, start_date y end_date son obligatorios")
            continue
        if end <= start:
            result.add_error(r, "end_date debe ser posterior a start_date")
            continue

        sku = cell_str(row, "product_sku")
        pid = cell_str(row, "product_id")
        product = None
        if pid:
            product = Product.objects.filter(organization=organization, id=pid).first()
        if product is None and sku:
            product = Product.objects.filter(organization=organization, sku=sku).first()
        if product is None:
            result.add_error(r, "Producto no encontrado (product_sku / product_id)")
            continue

        dtype = cell_str(row, "discount_type") or "percent"
        if dtype not in {
            ProductDiscount.TYPE_PERCENT,
            ProductDiscount.TYPE_FIXED,
            ProductDiscount.TYPE_PRICE,
        }:
            result.add_error(r, f"discount_type inválido: {dtype}", "discount_type")
            continue

        try:
            with transaction.atomic():
                discount = ProductDiscount.objects.create(
                    organization=organization,
                    name=name,
                    discount_type=dtype,
                    discount_percentage=_parse_decimal(row.get("discount_percentage")),
                    discount_amount_cop=_parse_decimal(row.get("discount_amount_cop")),
                    discount_price=_parse_decimal(row.get("discount_price")),
                    start_time=start,
                    end_time=end,
                    is_flash_sale=cell_bool(row, "is_flash_sale", default=True),
                    is_active=cell_bool(row, "is_active", default=True),
                )
                discount.products.add(product)
                # Ajusta compare_at / price si es oferta de precio
                if dtype == ProductDiscount.TYPE_PERCENT and discount.discount_percentage:
                    base = product.price_cop
                    sale = discount.apply_to_price(base)
                    if not product.compare_at_price_cop:
                        product.compare_at_price_cop = base
                    product.price_cop = sale
                    product.save(update_fields=["price_cop", "compare_at_price_cop", "updated_at"])
                elif dtype == ProductDiscount.TYPE_PRICE and discount.discount_price is not None:
                    if not product.compare_at_price_cop:
                        product.compare_at_price_cop = product.price_cop
                    product.price_cop = discount.discount_price
                    product.save(update_fields=["price_cop", "compare_at_price_cop", "updated_at"])
                result.created += 1
        except Exception as exc:  # noqa: BLE001
            result.add_error(r, str(exc))
    return result


IMPORTERS = {
    "schedule": import_schedule,
    "players": import_players,
    "jobs": import_jobs,
    "products": import_products,
    "discounts": import_discounts,
}
