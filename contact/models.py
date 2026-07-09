from django.db import models

from authentication.models import User
from core.models import TimeStampedModel
from organizations.models import Organization


class ContactMessage(TimeStampedModel):
    """Mensaje enviado desde el formulario de contacto público."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_messages",
        verbose_name="Organización (tenant)",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_messages",
        verbose_name="Usuario autenticado",
    )

    name = models.CharField(max_length=120, verbose_name="Nombre")
    email = models.EmailField(verbose_name="Correo")
    subject = models.CharField(max_length=200, blank=True, verbose_name="Asunto")
    message = models.TextField(verbose_name="Mensaje")

    is_read = models.BooleanField(default=False, db_index=True, verbose_name="Leído")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")

    class Meta:
        db_table = "contact_messages"
        ordering = ["-created_at"]
        verbose_name = "Mensaje de contacto"
        verbose_name_plural = "Mensajes de contacto"

    def __str__(self):
        return f"{self.name} <{self.email}> — {self.subject or 'Sin asunto'}"
