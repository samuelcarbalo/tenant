"""Lógica de importación por módulo."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import slugify

from .parsing import (
    JOB_TYPE_CHOICES,
    RowImportError,
    default_job_expires,
    normalize_job_type,
    parse_bool,
    parse_optional_datetime,
    parse_optional_decimal,
    parse_optional_int,
)
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

    def formatted_errors(self, limit: int = 200) -> list[str]:
        lines: list[str] = []
        for err in self.errors[:limit]:
            row = err.get("row")
            msg = str(err.get("message") or "").strip()
            if msg.lower().startswith("fila "):
                lines.append(msg)
            elif row:
                lines.append(f"Fila {row}: {msg}")
            elif msg:
                lines.append(msg)
        return lines


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
        try:
            row_errors: list[tuple[str | None, str]] = []

            title = cell_str(row, "title")
            company = cell_str(row, "company_name")
            description = cell_str(row, "description")
            if not title:
                row_errors.append(("title", "El campo 'title' es obligatorio y está vacío."))
            if not company:
                row_errors.append(
                    ("company_name", "El campo 'company_name' es obligatorio y está vacío.")
                )
            if not description:
                row_errors.append(
                    ("description", "El campo 'description' es obligatorio y está vacío.")
                )

            expires = None
            try:
                expires = parse_optional_datetime(row.get("expires_at"), "expires_at")
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))

            salary_min = None
            salary_max = None
            try:
                salary_min = parse_optional_decimal(
                    row.get("salary_min"), "salary_min", salary=True
                )
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))
            try:
                salary_max = parse_optional_decimal(
                    row.get("salary_max"), "salary_max", salary=True
                )
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))

            remote = False
            is_external = False
            try:
                remote = parse_bool(row.get("remote"), "remote")
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))
            try:
                is_external = parse_bool(row.get("is_external"), "is_external")
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))

            job_type = normalize_job_type(row.get("job_type"))
            if job_type not in JOB_TYPE_CHOICES:
                row_errors.append(
                    (
                        "job_type",
                        f"El campo 'job_type' ({job_type}) no es válido. "
                        f"Use: {', '.join(sorted(JOB_TYPE_CHOICES))}.",
                    )
                )

            external_url = cell_str(row, "external_apply_url")
            if is_external and not external_url:
                row_errors.append(
                    (
                        "external_apply_url",
                        "El campo 'external_apply_url' es obligatorio cuando is_external es SÍ.",
                    )
                )

            if row_errors:
                for field, msg in row_errors:
                    result.add_error(r, msg, field)
                continue

            location = cell_str(row, "location")[:255]
            category = cell_str(row, "category")[:255]
            apply_url = (external_url or None)
            if apply_url and len(apply_url) > 2048:
                result.add_error(
                    r,
                    "El campo 'external_apply_url' excede 2048 caracteres.",
                    "external_apply_url",
                )
                continue

            with transaction.atomic():
                JobOffer.objects.create(
                    organization=organization,
                    posted_by=user,
                    title=title[:255],
                    company_name=company[:255],
                    description=description,
                    requirements=cell_str(row, "requirements"),
                    location=location,
                    remote=remote,
                    category=category,
                    job_type=job_type,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    expires_at=default_job_expires(expires),
                    is_active=True,
                    is_external=is_external,
                    external_apply_url=apply_url,
                )
            result.created += 1
        except Exception as exc:  # noqa: BLE001
            result.add_error(r, f"Error en la fila {r}: {exc}", None)
    return result


def import_products(*, rows: list[dict], organization, user) -> ImportResult:
    from ecommerce.models import Category, Product, SubCategory

    result = ImportResult()
    for row in rows:
        r = int(row.get("_row") or 0)
        try:
            row_errors: list[tuple[str | None, str]] = []

            name = cell_str(row, "name")
            if not name:
                row_errors.append(("name", "El campo 'name' es obligatorio y está vacío."))

            price = None
            try:
                price = parse_optional_decimal(row.get("price_cop"), "price_cop")
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))
            if price is None and not any(f == "price_cop" for f, _ in row_errors):
                row_errors.append(
                    ("price_cop", "El campo 'price_cop' es obligatorio y está vacío.")
                )

            compare_at = None
            try:
                compare_at = parse_optional_decimal(
                    row.get("compare_at_price_cop"), "compare_at_price_cop"
                )
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))

            stock = 0
            try:
                stock = parse_optional_int(row.get("stock"), "stock", default=0) or 0
                if stock < 0:
                    row_errors.append(("stock", "El campo 'stock' no puede ser negativo."))
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))

            is_featured = False
            is_published = True
            try:
                is_featured = parse_bool(row.get("is_featured"), "is_featured")
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))
            try:
                is_published = parse_bool(row.get("is_published"), "is_published", default=True)
            except RowImportError as exc:
                row_errors.append((exc.field, str(exc)))

            if row_errors:
                for field, msg in row_errors:
                    result.add_error(r, msg, field)
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

            payload = {
                "name": name,
                "description": cell_str(row, "description"),
                "short_description": cell_str(row, "short_description")[:300],
                "sku": sku,
                "price_cop": price,
                "compare_at_price_cop": compare_at,
                "stock": stock,
                "image_url": cell_str(row, "image_url"),
                "is_featured": is_featured,
                "is_published": is_published,
                "category": category,
                "subcategory": subcategory,
            }
            with transaction.atomic():
                if existing:
                    for k, v in payload.items():
                        setattr(existing, k, v)
                    existing.save()
                    result.updated += 1
                else:
                    Product.objects.create(
                        organization=organization,
                        created_by=user,
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
