"""Importación masiva Excel (.xlsx) para el panel de administración."""

__all__ = ("ImportExcelView", "ImportTemplateView", "ImportModulesListView")


def __getattr__(name: str):
    if name in __all__:
        from . import views

        return getattr(views, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
