from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class OrganizationMiddleware(MiddlewareMixin):
    """
    Middleware que agrega la organización actual al request
    y verifica el contexto multi-tenant.
    Admite resolución por slug (cabecera X-Tenant) o ID (cabecera X-Organization-ID).
    """
    def process_request(self, request):
        # Resolver cabeceras de organización
        org_slug = request.headers.get('X-Tenant')
        org_id = request.headers.get('X-Organization-ID')
        
        organization = None
        
        # Buscar por slug (cabecera X-Tenant)
        if org_slug:
            cache_key = f'org_slug_{org_slug}'
            try:
                organization = cache.get(cache_key)
            except Exception:
                logger.exception("Cache get falló para org slug=%s", org_slug)
                organization = None
            if not organization:
                from organizations.models import Organization
                try:
                    organization = Organization.objects.get(slug=org_slug, is_active=True)
                    try:
                        cache.set(cache_key, organization, 60 * 60 * 24)
                    except Exception:
                        logger.exception("Cache set falló para org slug=%s", org_slug)
                except Organization.DoesNotExist:
                    pass
        
        # Buscar por ID (cabecera X-Organization-ID) si no se resolvió por slug
        elif org_id:
            cache_key = f'org_id_{org_id}'
            try:
                organization = cache.get(cache_key)
            except Exception:
                logger.exception("Cache get falló para org id=%s", org_id)
                organization = None
            if not organization:
                from organizations.models import Organization
                try:
                    organization = Organization.objects.get(id=org_id, is_active=True)
                    try:
                        cache.set(cache_key, organization, 60 * 60 * 24)
                    except Exception:
                        logger.exception("Cache set falló para org id=%s", org_id)
                except Organization.DoesNotExist:
                    pass

        # Fallback: Usar la organización del usuario si está autenticado
        if not organization and hasattr(request, 'user') and request.user.is_authenticated:
            organization = request.user.organization

        request.current_organization = organization

        # Validación de seguridad: el usuario no superusuario solo puede acceder a su propia organización
        if organization and hasattr(request, 'user') and request.user.is_authenticated:
            if not request.user.is_superuser and request.user.organization_id != organization.id:
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
