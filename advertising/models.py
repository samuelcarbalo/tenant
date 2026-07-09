from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from core.models import TimeStampedModel
from authentication.models import User
from sports.models import Tournament


class TournamentSponsorship(TimeStampedModel):
    """Patrocinio exclusivo de un torneo (todas las pantallas hijas)."""

    PLAN_CHOICES = [
        ("week", "Semana"),
        ("month", "Mes"),
        ("bimester", "Bimestre"),
    ]
    STATUS_CHOICES = [
        ("active", "Activo"),
        ("expired", "Expirado"),
        ("cancelled", "Cancelado"),
    ]

    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name="sponsorships",
    )
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tournament_sponsorships",
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.URLField()
    link_url = models.URLField(blank=True)

    start_date = models.DateField()
    end_date = models.DateField()
    credits_spent = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="active", db_index=True
    )

    class Meta:
        db_table = "tournament_sponsorships"
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["tournament", "status", "end_date"]),
        ]

    def __str__(self):
        return f"{self.title} → {self.tournament.name} ({self.get_plan_display()})"

    @property
    def is_active_now(self) -> bool:
        if self.status != "active":
            return False
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date

    @property
    def days_remaining(self) -> int:
        if not self.is_active_now:
            return 0
        return max(0, (self.end_date - timezone.now().date()).days)

    def mark_expired_if_needed(self):
        today = timezone.now().date()
        if self.status == "active" and self.end_date < today:
            self.status = "expired"
            self.save(update_fields=["status", "updated_at"])
            return True
        return False


class ClassifiedAdCampaign(TimeStampedModel):
    """Campaña publicitaria por alcance en empleos, inmuebles o eventos."""

    CONTENT_TYPES = [
        ("job", "Empleo"),
        ("real_estate", "Bienes raíces"),
        ("event", "Evento"),
    ]
    STATUS_CHOICES = [
        ("active", "Activa"),
        ("completed", "Completada"),
        ("expired", "Expirada"),
        ("cancelled", "Cancelada"),
    ]

    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ad_campaigns",
    )
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPES)
    content_type_ref = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey("content_type_ref", "object_id")

    plan = models.CharField(max_length=20)
    position = models.CharField(max_length=30)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.URLField()
    link_url = models.URLField(blank=True)

    target_reach = models.PositiveIntegerField(default=100)
    frequency_cap = models.PositiveIntegerField(default=5)
    unique_views = models.PositiveIntegerField(default=0)
    total_impressions = models.PositiveIntegerField(default=0)

    start_date = models.DateField()
    end_date = models.DateField()
    credits_spent = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="active", db_index=True
    )

    class Meta:
        db_table = "classified_ad_campaigns"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.title} ({self.get_content_type_display()})"

    @property
    def is_active_now(self) -> bool:
        if self.status != "active":
            return False
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date

    @property
    def max_impressions(self) -> int:
        return self.target_reach * self.frequency_cap

    @property
    def days_remaining(self) -> int:
        if not self.is_active_now:
            return 0
        return max(0, (self.end_date - timezone.now().date()).days)


class AdViewerImpression(TimeStampedModel):
    """Registro de impresiones por espectador (alcance único + frequency cap)."""

    campaign = models.ForeignKey(
        ClassifiedAdCampaign,
        on_delete=models.CASCADE,
        related_name="viewer_impressions",
    )
    viewer_hash = models.CharField(max_length=64, db_index=True)
    impression_count = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "ad_viewer_impressions"
        unique_together = [["campaign", "viewer_hash"]]
