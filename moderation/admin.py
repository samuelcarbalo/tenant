from django.contrib import admin

from moderation.models import ReportePublicacion


@admin.register(ReportePublicacion)
class ReportePublicacionAdmin(admin.ModelAdmin):
    list_display = ("id", "reporter", "content_type", "object_id", "reason", "created_at")
    list_filter = ("reason", "content_type")
    search_fields = ("reporter__email", "object_id")
    readonly_fields = ("created_at",)
