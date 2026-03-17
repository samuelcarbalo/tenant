from rest_framework import serializers
from .models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    """
    Serializer base para organizaciones.
    """
    user_count = serializers.IntegerField(source='users.count', read_only=True)
    class Meta:
        model = Organization
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'logo',
            'primary_color',
            'profile_schema',
            'max_users',
            'is_verified',
            'settings',
            'user_count',
            'created_at',
            'updated_at',
            'is_active'
        ]
        read_only_fields = [
            'id',
            'is_verified',
            'is_active'
        ]

class OrganizationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer para crear organizaciones (registro).
    """
    class Meta:
        model = Organization
        fields = [
            'name',
            'slug',
            'description'
        ]

    def validate_slug(self,value):
        if Organization.objects.filter(slug=value).exists():
            raise serializers.ValidationError('Slug already exists')
        return value

class OrganizationProfileSchemaSerializer(serializers.ModelSerializer):
    """
    Serializer para actualizar el schema de perfiles dinámicos.
    """
    class Meta:
        model = Organization
        fields = ['profile_schema']
    
    def validate_profile_schema(self,value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('El schema debe ser un objeto JSON.')

        fields = value.get('fields', [])
        if not isinstance(fields, list):
            raise serializers.ValidationError('El schema debe tener una lista de campos.')

        for field in fields:
            if 'name' not in field or 'type' not in field:
                raise serializers.ValidationError('Cada campo debe tener un nombre y un tipo.')
        return value
        