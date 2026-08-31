"""Importación masiva Excel (.xlsx) para el panel de administración."""

from .headers import IMPORT_MODULES, TEMPLATE_HEADERS
from .views import ImportExcelView, ImportTemplateView

__all__ = [
    "IMPORT_MODULES",
    "TEMPLATE_HEADERS",
    "ImportExcelView",
    "ImportTemplateView",
]
