from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException
from rest_framework import status


class OrganizationRequieredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Organization is required'
    default_code = 'organization_required'

def custom_exception_handler(exc, context):
    """
    Handler personalizado para formatear errores consistentemente.
    """
    response = exception_handler(exc, context)
    if response is not None:
        #formato estandar de errores
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