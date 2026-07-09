from django.urls import path

from moderation.views import ReportViewSet

urlpatterns = [
    path("reports/", ReportViewSet.as_view({"post": "create"}), name="create-report"),
]
