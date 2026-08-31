import uuid
from datetime import timedelta
from django.db import models
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.db.models import F
from core.models import TimeStampedModel
from organizations.models import Organization
from authentication.models import User


class JobOffer(TimeStampedModel):
    """
    Oferta de empleo publicada por reclutadores (managers).
    """

    # Relaciones
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="job_offers",
    )
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posted_jobs",
    )
    # Información básica
    title = models.CharField(max_length=255, db_index=True)
    company_name = models.CharField(max_length=255)
    description = models.TextField()
    requirements = models.TextField(blank=True)

    # Ubicación y tipo
    location = models.CharField(max_length=255, blank=True)
    remote = models.BooleanField(default=False)
    category = models.CharField(max_length=255, blank=True)
    benefits = models.JSONField(default=list, blank=True)
    job_type = models.CharField(
        max_length=20,
        choices=[
            ("full_time", "Tiempo completo"),
            ("part_time", "Medio tiempo"),
            ("contract", "Contrato"),
            ("freelance", "Freelance"),
            ("internship", "Prácticas"),
        ],
        default="full_time",
    )

    # Salario (opcional)
    salary_min = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    salary_max = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3, default="COP")

    # Skills/Palabras clave (JSON para flexibilidad)
    skills = models.JSONField(default=list, blank=True)

    # Ofertas externas (postulación en sitio de terceros)
    is_external = models.BooleanField(default=False, db_index=True)
    external_apply_url = models.URLField(max_length=2048, blank=True, null=True)

    # Fechas importantes
    posted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="Caduca automáticamente 30 días después de la creación si no se indica otra fecha."
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False)

    MODERATION_STATUS_CHOICES = [
        ("approved", "Aprobada"),
        ("pendiente_revision", "Pendiente revisión"),
        ("rejected", "Rechazada"),
    ]
    moderation_status = models.CharField(
        max_length=32,
        choices=MODERATION_STATUS_CHOICES,
        default="approved",
        db_index=True,
    )

    # Contadores
    views_count = models.PositiveIntegerField(default=0)
    applications_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "job_offers"
        ordering = ["-posted_at"]
        indexes = [
            models.Index(fields=["organization", "is_active", "expires_at"]),
            models.Index(fields=["skills"]),
            models.Index(fields=["job_type", "location"]),
            models.Index(fields=["is_external", "expires_at"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.company_name}"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            base = self.created_at or timezone.now()
            self.expires_at = base + timedelta(days=30)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def days_remaining(self):
        if self.is_expired:
            return 0
        return (self.expires_at - timezone.now()).days

    def renew(self, days=30):
        """Renovar la oferta por X días más"""
        self.expires_at = timezone.now() + timedelta(days=days)
        self.is_active = True
        self.save()


class JobApplication(TimeStampedModel):
    """
    Postulación de un usuario a una oferta de empleo.
    """

    offer = models.ForeignKey(
        JobOffer, on_delete=models.CASCADE, related_name="applications"
    )
    applicant = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="job_applications"
    )

    # CV del usuario (PDF, máx 1MB). Opcional para postulaciones externas.
    cv_file = models.FileField(
        upload_to="cvs/%Y/%m/",
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf"]),
        ],
        help_text="PDF máximo 1MB",
        blank=True,
        null=True,
    )
    # Mensaje opcional del postulante
    cover_letter = models.TextField(blank=True)
    # Estado de la postulación
    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("reviewing", "En revisión"),
        ("interview", "Entrevista"),
        ("rejected", "Rechazado"),
        ("hired", "Contratado"),
        ("shortlisted", "Preseleccionar"),
        ("redirected", "Redirigida / Aplicada externamente"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    # Notas del reclutador
    recruiter_notes = models.TextField(blank=True)

    # Fecha de postulación
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "job_applications"
        unique_together = [
            "offer",
            "applicant",
        ]  # Un usuario solo puede postularse una vez por oferta
        ordering = ["-applied_at"]

    def __str__(self):
        return f"Postulación de {self.applicant.username} a {self.offer.title}"

    def clean(self):
        # Validar que el CV no exceda 1MB
        if self.cv_file and self.cv_file.size > 1024 * 1024:  # 1MB
            raise models.ValidationError("El archivo no puede exceder 1MB.")

        # Validar que la oferta no esté expirada
        if self.offer.is_expired:
            raise models.ValidationError("Esta oferta ha expirado.")


class JobOfferHistory(models.Model):
    """
    Traza analítica (big data) de vacantes: sobrevive a la depuración de JobOffer.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_job_id = models.UUIDField(unique=True, db_index=True)
    title = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255)
    published_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_offer_history",
    )
    created_at = models.DateTimeField(db_index=True)
    expired_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_external = models.BooleanField(default=False, db_index=True)
    external_apply_url = models.URLField(max_length=2048, blank=True, null=True)
    total_applications_count = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    is_purged = models.BooleanField(default=False, db_index=True)
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "job_offer_history"
        ordering = ["-created_at"]
        verbose_name = "Historial de oferta"
        verbose_name_plural = "Historial de ofertas"
        indexes = [
            models.Index(fields=["is_external", "created_at"]),
            models.Index(fields=["is_purged", "expired_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.original_job_id})"


@receiver(post_save, sender=JobOffer)
def sync_job_offer_history(sender, instance, **kwargs):
    from .services import upsert_job_offer_history

    upsert_job_offer_history(instance)


@receiver(pre_delete, sender=JobOffer)
def snapshot_job_offer_history_on_delete(sender, instance, **kwargs):
    from .services import upsert_job_offer_history

    upsert_job_offer_history(instance, is_purged=True)


@receiver(post_save, sender=JobApplication)
def update_application_count(sender, instance, created, **kwargs):
    if created:
        # Usamos F() para actualizar en la base de datos de forma atómica
        # Esto evita que dos procesos simultáneos sobreescriban el valor
        JobOffer.objects.filter(id=instance.offer.id).update(
            applications_count=F("applications_count") + 1
        )
        offer = JobOffer.objects.filter(id=instance.offer.id).first()
        if offer:
            from .services import upsert_job_offer_history

            upsert_job_offer_history(offer)
