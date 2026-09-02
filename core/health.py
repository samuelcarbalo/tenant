"""Probes de liveness/readiness sin acceso a base de datos."""

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@csrf_exempt
@require_http_methods(["GET", "HEAD"])
def healthz(request):
    """
    Health check ultraligero para Render/nginx durante deploys.
    No consulta PostgreSQL, Redis ni cache.
    """
    if request.method == "HEAD":
        return HttpResponse(status=200)
    return JsonResponse({"status": "healthy"})
