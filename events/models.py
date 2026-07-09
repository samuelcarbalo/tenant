from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from authentication.models import User
from core.models import TimeStampedModel
from organizations.models import Organization


class EventListing(TimeStampedModel):
    """Evento publicitario / agenda local."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="event_listings",
    )
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posted_events",
    )

    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=280, unique=True)
    description = models.TextField()

    CATEGORY_CHOICES = [
        ("feria", "Feria"),
        ("concierto", "Concierto"),
        ("negocios", "Negocios"),
        ("cultural", "Cultural"),
        ("gastronomico", "Gastronómico"),
        ("deportivo", "Deportivo"),
        ("otro", "Otro"),
    ]
    event_category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="otro"
    )

    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=500, blank=True)
    is_online = models.BooleanField(default=False)
    online_url = models.URLField(blank=True)

    cover_image = models.URLField(blank=True)
    organizer_name = models.CharField(max_length=255, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_email = models.EmailField(blank=True)
    external_link = models.URLField(blank=True)
    price_info = models.CharField(max_length=255, blank=True, default="Gratis")

    posted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True, db_index=True)

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

    views_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "event_listings"
        ordering = ["start_datetime"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:240] or "evento"
            slug = base
            n = 1
            while EventListing.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def days_remaining(self) -> int:
        if self.is_expired:
            return 0
        return max(0, (self.expires_at - timezone.now()).days)
