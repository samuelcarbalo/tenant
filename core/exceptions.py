import logging

from django.core.exceptions import FieldError
from django.db import DatabaseError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class OrganizationRequieredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Organization is required'
    default_code = 'organization_required'


def _format_error_payload(status_code, field, message):
    return {
        'success': False,
        'error': [{'field': field, 'message': message}],
        'status_code': status_code,
    }


def custom_exception_handler(exc, context):
    """
    Handler personalizado para formatear errores consistentemente.
    Las excepciones no controladas (p. ej. ProgrammingError por tablas
    inexistentes) se devuelven como JSON en lugar de un 500 HTML crudo.
    """
    response = exception_handler(exc, context)
    if response is not None:
        if isinstance(response.data, dict):
            errors = []
            for field, value in response.data.items():
                if isinstance(value, list):
                    errors.extend([{'field': field, 'message': v} for v in value])
                else:
                    errors.append({'field': field, 'message': value})
            response.data = {
                'success': False,
                'error': errors,
                'status_code': response.status_code
            }
        return response

    logger.exception("Unhandled API exception: %s", exc)
    if isinstance(exc, (DatabaseError, FieldError)):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        message = (
            "Servicio temporalmente no disponible. "
            "Si el error persiste, verifica las migraciones de base de datos."
        )
        field = 'database'
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        message = "Error interno del servidor. Intenta de nuevo."
        field = 'server'

    return Response(
        _format_error_payload(status_code, field, message),
        status=status_code,
    )