from datetime import date, datetime

from django.test import SimpleTestCase
from django.utils import timezone

from authentication.admin_import.parsing import (
    RowImportError,
    parse_bool,
    parse_optional_datetime,
    parse_optional_decimal,
)


class ParseBoolTests(SimpleTestCase):
    def test_true_variants(self):
        for raw in (True, 1, "true", "1", "SI", "yes", "verdadero"):
            self.assertIs(parse_bool(raw, "remote"), True)

    def test_false_and_empty(self):
        self.assertIs(parse_bool("", "remote"), False)
        self.assertIs(parse_bool(None, "is_external"), False)
        self.assertIs(parse_bool("no", "remote"), False)
        self.assertIs(parse_bool("maybe", "remote"), False)


class ParseDatetimeTests(SimpleTestCase):
    def test_empty_is_none(self):
        self.assertIsNone(parse_optional_datetime("", "expires_at"))
        self.assertIsNone(parse_optional_datetime(None, "expires_at"))

    def test_iso_and_latin_strings(self):
        iso = parse_optional_datetime("2026-12-31", "expires_at")
        latin = parse_optional_datetime("31/12/2026", "expires_at")
        dotted = parse_optional_datetime("31.12.2026", "expires_at")
        self.assertEqual(iso.date(), date(2026, 12, 31))
        self.assertEqual(latin.date(), date(2026, 12, 31))
        self.assertEqual(dotted.date(), date(2026, 12, 31))
        self.assertTrue(timezone.is_aware(iso))

    def test_datetime_and_date_instances(self):
        naive = datetime(2026, 5, 1, 8, 30)
        parsed = parse_optional_datetime(naive, "expires_at")
        self.assertTrue(timezone.is_aware(parsed))
        self.assertEqual(parse_optional_datetime(date(2026, 5, 1), "expires_at").date(), date(2026, 5, 1))

    def test_excel_serial(self):
        parsed = parse_optional_datetime(44927, "expires_at")  # 2023-01-01-ish
        self.assertIsNotNone(parsed)
        self.assertTrue(timezone.is_aware(parsed))

    def test_invalid_raises_row_error(self):
        with self.assertRaises(RowImportError) as ctx:
            parse_optional_datetime("no-es-fecha", "expires_at")
        self.assertEqual(ctx.exception.field, "expires_at")


class ParseDecimalTests(SimpleTestCase):
    def test_empty_is_none(self):
        self.assertIsNone(parse_optional_decimal("", "salary_min", salary=True))
        self.assertIsNone(parse_optional_decimal(None, "salary_max", salary=True))

    def test_numeric_and_formatted(self):
        self.assertEqual(parse_optional_decimal(1500000, "salary_min", salary=True), 1500000)
        self.assertEqual(
            parse_optional_decimal("1,500,000", "salary_min", salary=True),
            1500000,
        )
        self.assertEqual(
            parse_optional_decimal("1.500.000", "salary_min", salary=True),
            1500000,
        )

    def test_invalid_raises(self):
        with self.assertRaises(RowImportError):
            parse_optional_decimal("abc", "salary_min", salary=True)
