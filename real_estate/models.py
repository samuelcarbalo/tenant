from datetime import timedelta
from django.db import models
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from core.models import TimeStampedModel
from organizations.models import Organization
from authentication.models import User


class RealEstateOffer(TimeStampedModel):
    """
    Oferta de bienes raíces publicada por managers de organizaciones.
    """

    CATEGORY_CHOICES = [
        ("sale", "Venta"),
        ("rent", "Alquiler"),
    ]

    PROPERTY_TYPE_CHOICES = [
        ("house", "Casa"),
        ("apartment", "Apartamento"),
        ("lot", "Lote/Terreno"),
        ("commercial", "Local Comercial"),
        ("farm", "Finca"),
    ]

    # Relaciones
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="real_estate_offers",
    )
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posted_real_estate",
    )

    # Detalles de la propiedad
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2, db_index=True)
    currency = models.CharField(max_length=3, default="COP")
    
    # Carga de Imagen Principal (Validada por extensiones sin Pillow)
    image = models.FileField(
        upload_to="real_estate/%Y/%m/",
        validators=[
            FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"]),
        ],
        null=True,
        blank=True,
        help_text="Imagen principal de la propiedad (JPG, PNG, WebP)"
    )

    location = models.CharField(max_length=255, blank=True, db_index=True)
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="sale",
        db_index=True,
    )
    property_type = models.CharField(
        max_length=20,
        choices=PROPERTY_TYPE_CHOICES,
        default="house",
        db_index=True,
    )

    # Datos de contacto
    contact_name = models.CharField(max_length=255, blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    contact_email = models.EmailField(blank=True)

    # Fechas y control
    posted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    is_featured = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0)

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

    class Meta:
        db_table = "real_estate_offers"
        ordering = ["-posted_at"]
        indexes = [
            models.Index(fields=["organization", "is_active", "expires_at"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.price} {self.currency}"

    def save(self, *args, **kwargs):
        # Asignar 30 días de expiración si no viene definido
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=30)
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
