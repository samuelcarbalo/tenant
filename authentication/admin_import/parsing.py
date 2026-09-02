"""Parseo seguro de celdas Excel → tipos Python (sin tumbar el proceso)."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

TRUE_VALUES = {
    "true",
    "1",
    "si",
    "sí",
    "yes",
    "y",
    "s",
    "x",
    "on",
    "verdadero",
    "vero",
}
FALSE_VALUES = {"false", "0", "no", "n", "off", "falso"}
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%Y/%m/%d",
    "%d.%m.%Y",
)

# DecimalField(max_digits=10, decimal_places=2) en JobOffer
SALARY_ABS_MAX = Decimal("99999999.99")


class RowImportError(ValueError):
    """Error recuperable de una celda/fila del Excel."""

    def __init__(self, message: str, field: str | None = None, row: int | None = None):
        super().__init__(message)
        self.field = field
        self.row = row


def display_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat(timespec="minutes")
    try:
        return str(value).strip()
    except Exception:
        return repr(value)


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _from_excel_serial(serial: float) -> datetime | None:
    try:
        from openpyxl.utils.datetime import from_excel

        converted = from_excel(serial)
    except Exception:
        return None
    if isinstance(converted, datetime):
        return converted
    if isinstance(converted, date):
        return datetime(converted.year, converted.month, converted.day)
    return None


def _from_text(text: str) -> datetime | None:
    variants = [text.strip()]
    stripped = text.strip()
    if stripped.count(".") == 2 and "/" not in stripped:
        variants.append(stripped.replace(".", "/", 2))
    for candidate in variants:
        dt = parse_datetime(candidate)
        if dt is not None:
            return dt
        parsed = parse_date(candidate)
        if parsed is not None:
            return datetime(parsed.year, parsed.month, parsed.day)
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    try:
        from dateutil.parser import parse as dateutil_parse

        return dateutil_parse(stripped, dayfirst=True, fuzzy=False)
    except Exception:
        return None


def parse_optional_datetime(value: Any, field: str) -> datetime | None:
    """
    Convierte fecha Excel/string a datetime aware.
    Vacío → None. Valor presente e inválido → RowImportError (nunca 500).
    """
    if is_empty(value):
        return None

    try:
        dt: datetime | None = None
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, date):
            dt = datetime(value.year, value.month, value.day)
        elif isinstance(value, time):
            today = timezone.localdate()
            dt = datetime.combine(today, value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            serial = float(value)
            if 1 <= serial <= 100000:
                dt = _from_excel_serial(serial)
            if dt is None:
                dt = _from_text(str(value).strip())
        else:
            dt = _from_text(str(value).strip())

        if dt is None:
            shown = display_cell(value)
            raise RowImportError(
                f"La fecha '{field}' ({shown}) no tiene un formato válido (se espera AAAA-MM-DD).",
                field,
            )
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    except RowImportError:
        raise
    except Exception as exc:
        shown = display_cell(value)
        raise RowImportError(
            f"La fecha '{field}' ({shown}) no tiene un formato válido (se espera AAAA-MM-DD).",
            field,
        ) from exc


def _normalize_number_text(text: str) -> str:
    cleaned = (
        text.replace("$", "")
        .replace("COP", "")
        .replace("cop", "")
        .replace("\xa0", "")
        .strip()
    )
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        return ""
    if cleaned.count(",") == 1 and cleaned.count(".") >= 1:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") >= 1 and cleaned.count(".") == 0:
        _whole, frac = cleaned.split(",", 1) if cleaned.count(",") == 1 else ("", "")
        if cleaned.count(",") == 1 and len(frac) in (1, 2):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    return cleaned


def parse_optional_decimal(value: Any, field: str, *, salary: bool = False) -> Decimal | None:
    if is_empty(value):
        return None
    try:
        if isinstance(value, bool):
            raise _numeric_error(field, salary)
        if isinstance(value, float) and value != value:
            return None
        parsed: Decimal
        if isinstance(value, Decimal):
            parsed = value
        elif isinstance(value, (int, float)):
            parsed = Decimal(str(value))
        else:
            text = _normalize_number_text(str(value))
            if not text:
                return None
            parsed = Decimal(text)
        if salary and abs(parsed) > SALARY_ABS_MAX:
            raise RowImportError(
                f"El salario '{field}' ({parsed}) excede el máximo permitido.",
                field,
            )
        return parsed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if salary else parsed
    except RowImportError:
        raise
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise _numeric_error(field, salary) from exc


def parse_optional_int(value: Any, field: str, default: int | None = None) -> int | None:
    if is_empty(value):
        return default
    try:
        if isinstance(value, bool):
            raise RowImportError(f"El campo '{field}' debe ser un valor numérico.", field)
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value == value and value.is_integer():
            return int(value)
        text = _normalize_number_text(str(value))
        parsed = Decimal(text)
        if parsed != parsed.to_integral_value():
            raise RowImportError(f"El campo '{field}' debe ser un valor numérico entero.", field)
        return int(parsed)
    except RowImportError:
        raise
    except (InvalidOperation, ValueError, TypeError, AttributeError) as exc:
        raise RowImportError(f"El campo '{field}' debe ser un valor numérico.", field) from exc


def parse_bool(value: Any, field: str = "", default: bool = False) -> bool:
    """Convierte la celda a bool. Vacío → default. Valores no reconocidos → False."""
    if is_empty(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value in (0, 1):
        return bool(int(value))
    try:
        raw = str(value).strip().lower()
    except Exception:
        return default
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    return default


def default_job_expires(value: datetime | None) -> datetime:
    if value is not None:
        return value
    return timezone.now() + timedelta(days=30)


def _numeric_error(field: str, salary: bool) -> RowImportError:
    if salary:
        return RowImportError(f"El salario '{field}' debe ser un valor numérico.", field)
    return RowImportError(f"El campo '{field}' debe ser un valor numérico.", field)


JOB_TYPE_CHOICES = {
    "full_time",
    "part_time",
    "contract",
    "freelance",
    "internship",
}

JOB_TYPE_MAP = {
    "tiempo completo": "full_time",
    "medio tiempo": "part_time",
    "contrato": "contract",
    "prestacion de servicios": "contract",
    "freelance": "freelance",
    "pasantia": "internship",
    "practicas": "internship",
}


def _fold_job_type(value: str) -> str:
    nfkd = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return " ".join(ascii_text.lower().strip().split())


def normalize_job_type(value: Any, default: str = "full_time") -> str:
    """Mapea etiquetas en español (o el código canónico) al choice del modelo."""
    if is_empty(value):
        return default
    try:
        raw = _fold_job_type(str(value))
    except Exception:
        return default
    if not raw:
        return default
    if raw in JOB_TYPE_CHOICES:
        return raw
    underscored = raw.replace(" ", "_")
    if underscored in JOB_TYPE_CHOICES:
        return underscored
    return JOB_TYPE_MAP.get(raw, raw)
