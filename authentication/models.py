import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel
from organizations.models import Organization
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Modelo de Usuario con soporte multi-organización.
    """

    # Campo único global (autogenerado, no se usa para login)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Campos de login (pueden repetirse entre organizaciones)
    email = models.EmailField(db_index=True)  # Sin unique=True
    username = models.CharField(max_length=150, db_index=True)  # Sin unique=True

    # Información personal
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)

    # Organización (clave para multi-tenancy)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,  # Null temporalmente durante registro
        blank=True,
    )

    # Roles dentro de la organización
    ROLE_CHOICES = [
        ("admin", "Administrador"),
        ("manager", "Gerente"),
        ("user", "Usuario"),
    ]
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default="user", db_index=True
    )

    # Estado
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False)
    company_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Nombre de la empresa si el usuario es tipo empresa",
    )
    # Opcional: campo para distinguir tipo de usuario
    USER_TYPE_CHOICES = [
        ("person", "Persona"),
        ("company", "Empresa"),
    ]
    user_type = models.CharField(
        max_length=20, choices=USER_TYPE_CHOICES, default="person"
    )
    # Metadatos
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)

    # Campos para JWT tracking
    jti = models.CharField(max_length=255, blank=True, db_index=True)

    # Campo único global para Django (no se muestra al usuario)
    identifier = models.CharField(max_length=255, unique=True, editable=False)

    USERNAME_FIELD = "identifier"
    REQUIRED_FIELDS = ["email", "username"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        indexes = [
            models.Index(fields=["organization", "is_active"]),
            models.Index(fields=["email", "organization"]),
            models.Index(fields=["role", "organization"]),
        ]
        constraints = [
            # Email único por organización
            models.UniqueConstraint(
                fields=["email", "organization"],
                name="unique_email_per_org",
                condition=models.Q(organization__isnull=False),
            ),
            # Email único global solo para superusuarios (organization=None)
            models.UniqueConstraint(
                fields=["email"],
                name="unique_email_superuser",
                condition=models.Q(organization__isnull=True, is_superuser=True),
            ),
        ]

    def __str__(self):
        return f"{self.email} ({self.organization.name if self.organization else 'No Org'})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def get_organization_context(self):
        """
        Retorna el contexto de organización para queries filtradas.
        """
        return {"organization_id": self.organization_id}

    def has_org_permission(self, permission_codename):
        """
        Verifica permisos específicos dentro de la organización.
        """
        if self.is_superuser:
            return True
        if self.role == "admin":
            return True
        if self.role == "manager" and permission_codename.startswith("view_"):
            return True
        return False

    def save(self, *args, **kwargs):
        # Generar identifier único si no existe
        if not self.identifier:
            # Usar UUID para garantizar unicidad global
            self.identifier = str(uuid.uuid4())
        super().save(*args, **kwargs)

    def get_username(self):
        return self.username  # Mostrar el username legible, no el identifier


class LoginAttempt(TimeStampedModel):
    """
    Tracking de intentos de login para seguridad.
    """

    email = models.EmailField(db_index=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, null=True, blank=True
    )

    class Meta:
        db_table = "login_attempts"
        ordering = ["-created_at"]
