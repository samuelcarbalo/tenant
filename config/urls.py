from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from organizations.views import OrganizationViewSet
from rest_framework.routers import DefaultRouter


@api_view(["GET"])
def api_root(request):
    return Response(
        {
            "message": "Multi-Tenant Django API",
            "version": "1.0.0",
            "endpoints": {
                "auth": "/api/v1/auth/",
                "profiles": "/api/v1/profiles/",
                "organizations": "/api/v1/organizations/",
            },
        }
    )


# Al inicio de config/urls.py
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("authentication.urls")),
    path("api/v1/profiles/", include("profiles.urls")),
    path(
        "api/v1/organizations/", include("organizations.urls")
    ),  # Sin 'organizations/' aquí
    path("api/v1/jobs/", include("jobs.urls")),
    path("api/v1/sports/", include("sports.urls")),
]
if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
