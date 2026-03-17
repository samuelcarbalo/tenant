from django.contrib.auth.models import BaseUserManager
from django.db import models

class UserManager(BaseUserManager):
    """
    Manager personalizado para el modelo User.
    """
    def create_user(self, email, username, password=None, organization=None, **extra_fields):
        """
        Crea y guarda un usuario con el email y contraseña dados.
        """
        if not email:
            raise ValueError('El email es requerido')
        if not username:
            raise ValueError('El username es requerido')
        email = self.normalize_email(email)
        if organization:
            from organizations.models import Organization
            if isinstance(organization, str):
                organization = Organization.objects.get(slug=organization)
        user = self.model(
            email=email,
            username=username,
            organization=organization,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, username, password=None, **extra_fields):
        """
        Crea y guarda un superusuario con el email y contraseña dados.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'admin')
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser=True')
        
        return self.create_user(email, username, password, **extra_fields)

    def get_by_organization(self, organization_id):
        """
        Retorna usuarios de una organización específica.
        """
        return self.select_related('organization').filter(
            organization_id=organization_id,
            is_active=True
        )
    def get_with_profile(self, organization_id):
        """
        Retorna usuarios con perfil de una organización específica.
        """
        return self.select_related('organization', 'profile')