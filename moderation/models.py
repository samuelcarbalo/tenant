import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class ReportePublicacion(models.Model):
    """Reporte de contenido inapropiado en publicaciones."""

    REASON_CHOICES = [
        ("fraude", "Fraude"),
        ("contenido_inapropiado", "Contenido Inapropiado"),
        ("discriminacion", "Discriminación"),
    ]

    REPORT_THRESHOLD = 3

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reportes_enviados",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")

    reason = models.CharField(max_length=32, choices=REASON_CHOICES)
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reportes_publicacion"
        ordering = ["-created_at"]
        unique_together = [["reporter", "content_type", "object_id"]]
        verbose_name = "Reporte de publicación"
        verbose_name_plural = "Reportes de publicación"

    def __str__(self):
        return f"Reporte {self.reason} — {self.content_type} {self.object_id}"
