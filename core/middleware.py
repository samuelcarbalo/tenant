from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache

class OrganizationMiddleware(MiddlewareMixin):
    """
    Middleware que agrega la organización actual al request
    y verifica el contexto multi-tenant.
    """
    def process_request(self, request):
        # Obtener organization_id del header o del usuario
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return None
        
        org_id = request.headers.get('X-Organization-ID')
        if not org_id:
            cache_key = f'org_{org_id}'
            organization = cache.get(cache_key)
            if not organization:
                from organizations.models import Organization
                try:
                    organization = Organization.objects.get(id=org_id, is_active=True)
                    cache.set(cache_key, organization, 60 * 60 * 24)
                except Organization.DoesNotExist:
                    request.current_organization = None
                    return None
            request.current_organization = organization
            if str(request.user.organization_id) != str(org_id) and not request.user.is_superuser:
                request.current_organization = None
                return None

class DebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        print("========== DEBUG MIDDLEWARE INICIADO ==========")

    def __call__(self, request):
        print(f"========== REQUEST: {request.method} {request.path} ==========")
        response = self.get_response(request)
        print(f"========== RESPONSE: {response.status_code} ==========")
        return response