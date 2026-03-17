from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Profile

User = get_user_model()

class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer base para perfiles.
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    organization_name = serializers.CharField(
        source='organization.name', 
        read_only=True
    )
    
    class Meta:
        model = Profile
        fields = [
            'id', 'user', 'user_email', 'user_name',
            'organization', 'organization_name',
            'bio', 'birth_date', 'location', 'department', 'job_title',
            'dynamic_data', 'avatar', 'preferences',
            'completion_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'organization', 'completion_percentage']

class ProfileCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para crear/actualizar perfiles con validación dinámica.
    """
    class Meta:
        model = Profile
        fields = [
            'bio', 'birth_date', 'location', 'department', 'job_title',
            'dynamic_data', 'avatar', 'preferences'
        ]
    def validate_dynamic_data(self, value):
        """
        Validar campos dinámicos contra el schema de la organización.
        """
        organization =  self.context['request'].user.organization

        if not organization:
            raise serializers.ValidationError('Usuario sin organización asignada.')
        
        # Validar que solo se envíen campos permitidos
        allowed_fields = {f['name'] for f in organization.get_profile_fields()}
        sent_fields = set(value.keys())
        
        invalid_fields = sent_fields - allowed_fields
        if invalid_fields:
            raise serializers.ValidationError(
                f'Campos no permitidos: {invalid_fields}. '
                f'Campos permitidos: {allowed_fields}'
            )
        # Validar tipos y requeridos
        is_valid, error = organization.validate_profile_data(value)
        if not is_valid:
            raise serializers.ValidationError(error)
        return value

    def update(self, instance, validated_data):
        # Merge dynamic_data en lugar de reemplazar
        if "dynamic_data" in validated_data:
            current_dynamic = instance.dynamic_data or {}
            current_dynamic.update(validated_data.pop('dynamic_data'))
            validated_data['dynamic_data'] = current_dynamic
            
        return super().update(instance, validated_data)

class ProfileListSerializer(serializers.ModelSerializer):
    """
    Serializer optimizado para listados (campos mínimos).
    """
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Profile
        fields = [
            'id', 'user_name', 'user_email', 'department',
            'job_title', 'avatar', 'completion_percentage'
        ]

class ProfileSearchSerializer(serializers.Serializer):
    """
    Serializer para búsqueda de perfiles.
    """
    query = serializers.CharField(required=True, min_length=2)
    department = serializers.CharField(required=False)
    fields = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )

    