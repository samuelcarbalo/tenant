from django.contrib import admin

from .models import JobApplication, JobOffer, JobOfferHistory


@admin.register(JobOffer)
class JobOfferAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "company_name",
        "is_external",
        "is_active",
        "expires_at",
        "applications_count",
    )
    list_filter = ("is_external", "is_active", "job_type")
    search_fields = ("title", "company_name")


@admin.register(JobOfferHistory)
class JobOfferHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "company_name",
        "is_external",
        "total_applications_count",
        "created_at",
        "expired_at",
        "is_purged",
    )
    list_filter = ("is_external", "is_purged")
    search_fields = ("title", "company_name")
    readonly_fields = (
        "original_job_id",
        "title",
        "company_name",
        "published_by",
        "created_at",
        "expired_at",
        "is_external",
        "external_apply_url",
        "total_applications_count",
        "metadata",
        "is_purged",
        "recorded_at",
    )


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ("offer", "applicant", "status", "applied_at")
    list_filter = ("status",)
