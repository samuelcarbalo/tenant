from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .admin_views import AdminUserViewSet
from .admin_import.views import ImportExcelView, ImportModulesListView, ImportTemplateView
from jobs.admin_views import JobOfferHistoryListView

router = DefaultRouter()
router.register(r"users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("import/modules/", ImportModulesListView.as_view(), name="admin-import-modules"),
    path(
        "templates/<str:module>/",
        ImportTemplateView.as_view(),
        name="admin-import-template",
    ),
    path(
        "import/<str:module>/",
        ImportExcelView.as_view(),
        name="admin-import-upload",
    ),
    path("jobs/history/", JobOfferHistoryListView.as_view(), name="admin-jobs-history"),
    path("", include(router.urls)),
]
