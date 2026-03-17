from django.db import models
from django.core.validators import RegexValidator
from core.models import TimeStampedModel


class Organization(TimeStampedModel):
    """
    Modelo de Organización para multi-tenancy.
    Cada usuario pertenece a una organización.
    """
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(unique=True, db_index=True)
    description = models.TextField(blank=True)
    
    # Configuración de la organización
    logo = models.URLField(blank=True)
    primary_color = models.CharField(
        max_length=7, 
        default='#3B82F6',
        validators=[RegexValidator(regex='^#[0-9A-Fa-f]{6}$')]
    )
    
    # Configuración de campos dinámicos para perfiles
    profile_schema = models.JSONField(
        default=dict,
        help_text='Schema JSON que define los campos dinámicos del perfil'
    )
    
    # Límites y configuración
    max_users = models.PositiveIntegerField(default=100)
    is_verified = models.BooleanField(default=False, db_index=True)
    
    # Metadata
    settings = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'organizations'
        verbose_name = 'Organización'
        verbose_name_plural = 'Organizaciones'
        indexes = [
            models.Index(fields=['slug', 'is_active']),
            models.Index(fields=['is_verified', 'created_at']),
        ]
    
    def __str__(self):
        return self.name
    
    def get_profile_fields(self):
        """
        Retorna los campos dinámicos configurados para perfiles.
        """
        return self.profile_schema.get('fields', [])
    
    def validate_profile_data(self, data):
        """
        Valida los datos del perfil contra el schema de la organización.
        """
        from jsonschema import validate, ValidationError as JSONSchemaValidationError
        
        schema = {
            "type": "object",
            "properties": {
                field['name']: {"type": field.get('type', 'string')}
                for field in self.get_profile_fields()
            },
            "required": [
                field['name'] for field in self.get_profile_fields() 
                if field.get('required', False)
            ]
        }
        
        try:
            validate(instance=data, schema=schema)
            return True, None
        except JSONSchemaValidationError as e:
            return False, str(e)