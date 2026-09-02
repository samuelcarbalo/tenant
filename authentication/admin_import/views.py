"""Endpoints de importación Excel y descarga de plantillas (solo staff/admin)."""

from __future__ import annotations

import logging
from zipfile import BadZipFile

from django.http import HttpResponse
from openpyxl.utils.exceptions import InvalidFileException
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import resolve_request_organization, user_is_platform_elevated

from .headers import IMPORT_MODULES, TEMPLATE_HEADERS, WRONG_TEMPLATE_MESSAGE, headers_match_module
from .importers import IMPORTERS
from .workbook import build_template_workbook, read_rows

logger = logging.getLogger(__name__)

INVALID_EXCEL_PAYLOAD = {
    "status": "error",
    "message": "El archivo subido no es un documento Excel válido (.xlsx o .xls).",
}


def _error_response(message: str, errors: list[str] | None = None, **extra):
    payload = {"status": "error", "message": message, "detail": message, **extra}
    if errors is not None:
        payload["errors"] = errors
        if errors:
            payload["detail"] = errors[0] if len(errors) == 1 else message
    return Response(payload, status=status.HTTP_400_BAD_REQUEST)


class IsPlatformAdmin(IsAdminUser):
    """IsAdminUser o role=admin de plataforma."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if user_is_platform_elevated(request.user):
            return True
        return bool(request.user.is_staff)


class ImportTemplateView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request, module: str):
        module = (module or "").strip().lower()
        if module not in IMPORT_MODULES:
            return Response(
                {
                    "detail": f"Módulo inválido. Use uno de: {', '.join(IMPORT_MODULES)}",
                    "modules": list(IMPORT_MODULES),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        buf = build_template_workbook(module)
        filename = f"chever_plantilla_{module}.xlsx"
        response = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Template-Headers"] = ",".join(TEMPLATE_HEADERS[module])
        return response


class ImportExcelView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, module: str):
        module = (module or "").strip().lower()
        if module not in IMPORT_MODULES:
            return Response(
                {
                    "detail": f"Módulo inválido. Use uno de: {', '.join(IMPORT_MODULES)}",
                    "modules": list(IMPORT_MODULES),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        upload = request.FILES.get("file") or request.FILES.get("excel")
        if not upload:
            return _error_response("Adjunte el archivo Excel en el campo 'file'.")
        if not str(upload.name).lower().endswith((".xlsx", ".xlsm", ".xls")):
            return Response(INVALID_EXCEL_PAYLOAD, status=status.HTTP_400_BAD_REQUEST)

        organization = resolve_request_organization(request)
        if organization is None:
            return _error_response("No se pudo resolver la organización (X-Tenant).")

        try:
            try:
                headers, rows = read_rows(upload)
            except (BadZipFile, InvalidFileException, ValueError, KeyError, OSError) as exc:
                logger.warning("Excel inválido en import/%s: %s", module, exc)
                return Response(INVALID_EXCEL_PAYLOAD, status=status.HTTP_400_BAD_REQUEST)

            if not headers_match_module(headers, module):
                return _error_response(WRONG_TEMPLATE_MESSAGE, [WRONG_TEMPLATE_MESSAGE])

            importer = IMPORTERS[module]
            result = importer(rows=rows, organization=organization, user=request.user)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fallo inesperado en import/%s", module)
            row_index = getattr(exc, "row", None) or 1
            detail = f"Error en la fila {row_index}: {exc}"
            return _error_response(detail, [detail])

        if result.errors:
            return _error_response(
                "Se encontraron errores al procesar el archivo Excel.",
                result.formatted_errors(),
                created=result.created,
                updated=result.updated,
                error_count=len(result.errors),
            )

        payload = {
            "status": "ok",
            "success": True,
            "message": "Importación completada.",
            "module": module,
            "organization": getattr(organization, "slug", None),
            **result.as_dict(),
        }
        return Response(payload, status=status.HTTP_200_OK)


class ImportModulesListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        return Response(
            {
                "modules": [
                    {"key": key, "headers": TEMPLATE_HEADERS[key]}
                    for key in IMPORT_MODULES
                ]
            }
        )
