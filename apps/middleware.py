from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache


class OrganizationMiddleware(MiddlewareMixin):
    """
    Middleware que agrega la organización actual al request
    y verifica el contexto multi-tenant.
    """
    def process_request(self, request):
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return None
        
        # Cachear la organización para evitar queries repetidos
        org_id = request.headers.get('X-Organization-ID')
        if org_id:
            cache_key = f'org_{org_id}'
            organization = cache.get(cache_key)
            
            if not organization:
                from organizations.models import Organization
                try:
                    organization = Organization.objects.get(id=org_id, is_active=True)
                    cache.set(cache_key, organization, 300)  # 5 minutos
                except Organization.DoesNotExist:
                    request.current_organization = None
                    return None
            
            request.current_organization = organization
            
            # Verificar que el usuario pertenezca a esta org
            if str(request.user.organization_id) != str(org_id) and not request.user.is_superuser:
                request.current_organization = None