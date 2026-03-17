import uuid
from django.db import models


class TimeStampedModel(models.Model):
    """
    Modelo base abstracto con campos de timestamp y UUID.
    Todos los modelos heredan de este para consistencia.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']