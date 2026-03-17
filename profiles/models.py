from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import JSONField

from core.models import TimeStampedModel
from organizations.models import Organization

User = get_user_model()

class Profile(TimeStampedModel):
    """
    Perfil de usuario con campos dinámicos basados en la organización.
    Utiliza JSONField para flexibilidad y mantiene campos comunes indexados.
    """
    # Relaciones
    # Relaciones
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        db_index=True
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='profiles',
        db_index=True
    )
    # Campos comunes indexados (búsquedas frecuentes)
    bio = models.TextField(blank=True)
    birth_date = models.DateField(null=True, blank=True, db_index=True)
    location = models.CharField(max_length=255, blank=True, db_index=True)
    department = models.CharField(max_length=100, blank=True, db_index=True)
    job_title = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Campos dinámicos configurables por organización
    dynamic_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Campos personalizados definidos por la organización'
    )
    
    # Avatar y preferencias
    avatar = models.URLField(blank=True)
    preferences = models.JSONField(default=dict, blank=True)
    
    # Metadatos de completitud
    completion_percentage = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'profiles'
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfiles'
        indexes = [
            models.Index(fields=['organization', 'department']),
            models.Index(fields=['organization', 'job_title']),
            models.Index(fields=['completion_percentage']),
            # Índice GIN para búsquedas en JSONField (PostgreSQL)
            models.Index(fields=['dynamic_data'], name='dynamic_data_gin_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'organization'],
                name='unique_user_profile_per_org'
            )
        ]

    def __str__(self):
        return f"Perfil de {self.user}"
    
    def clean(self):
        """
        Validar datos dinámicos contra el schema de la organización.
        """
        if self.organization and self.dynamic_data:
            is_valid = self.organization.validate_schema(self.dynamic_data)
            if not is_valid:
                raise ValidationError(f'Datos de perfil inválidos: {error}')

    def save(self, *args, **kwargs):
        # Calcular porcentaje de completitud
        self.calculate_completion()
        super().save(*args, **kwargs)

    def calculate_completion(self):
        """
        Calcula el porcentaje de campos completados.
        """
        fields = [
            self.bio,
            self.birth_date,
            self.location,
            self.department,
            self.job_title,
            self.avatar,
        ]
        completed = sum(1 for f in fields if f)

        # Incluir campos dinámicos requeridos
        if self.organization:
            requied_dynamic = [
                f['name'] for f in self.organization.get_profile_fields() if f.get('required', False)
            ]
            completed_dynamic = sum(
                1 for field in requied_dynamic if self.dynamic_data.get(field)
            )
            total = len(fields) + len(requied_dynamic)
            completed += completed_dynamic
        else:
            total = len(fields)
        self.completion_percentage = int((completed / total) * 100) if total > 0 else 0

    def get_full_profile(self):
        """
        Retorna el perfil completo incluyendo datos dinámicos formateados.
        """
        return {
            'id': str(self.id),
            'user': {
                'id': str(self.user.id),
                'email': self.user.email,
                'full_name': self.user.full_name,
            },
            'common_fields': {
                'bio': self.bio,
                'birth_date': self.birth_date,
                'location': self.location,
                'department': self.department,
                'job_title': self.job_title,
                'avatar': self.avatar,
            },
            'dynamic_fields': self.dynamic_data,
            'completion_percentage': self.completion_percentage,
            'preferences': self.preferences,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }