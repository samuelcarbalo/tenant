"""Endpoints de importación Excel y descarga de plantillas (solo staff/admin)."""

from __future__ import annotations

from django.http import HttpResponse
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import resolve_request_organization, user_is_platform_elevated

from .headers import IMPORT_MODULES, TEMPLATE_HEADERS
from .importers import IMPORTERS
from .workbook import build_template_workbook, read_rows


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
            return Response(
                {"detail": "Adjunte el archivo Excel en el campo 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not str(upload.name).lower().endswith((".xlsx", ".xlsm")):
            return Response(
                {"detail": "Solo se aceptan archivos .xlsx"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        organization = resolve_request_organization(request)
        if organization is None:
            return Response(
                {"detail": "No se pudo resolver la organización (X-Tenant)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            headers, rows = read_rows(upload)
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"detail": f"No se pudo leer el Excel: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expected = TEMPLATE_HEADERS[module]
        missing = [h for h in expected if h not in headers]
        if missing:
            return Response(
                {
                    "detail": "Encabezados incompletos.",
                    "missing_headers": missing,
                    "expected_headers": expected,
                    "received_headers": headers,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        importer = IMPORTERS[module]
        result = importer(rows=rows, organization=organization, user=request.user)
        payload = {
            "success": result.error_count == 0 or result.created + result.updated > 0,
            "module": module,
            "organization": getattr(organization, "slug", None),
            **result.as_dict(),
        }
        code = status.HTTP_200_OK if payload["success"] else status.HTTP_400_BAD_REQUEST
        if result.created or result.updated:
            code = status.HTTP_200_OK
        return Response(payload, status=code)


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
