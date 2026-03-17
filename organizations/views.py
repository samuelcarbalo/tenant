from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Count, Q
from django.core.cache import cache

from .models import Organization
from .serializers import (
    OrganizationSerializer, 
    OrganizationCreateSerializer,
    OrganizationProfileSchemaSerializer
)
from core.permissions import IsOrganizationAdmin

class OrganizationViewSet(viewsets.ModelViewSet):
    """
    ViewSet para operaciones de organización.
    """
    queryset = Organization.objects.all()
    lookup_field = 'slug'
    permission_classes = [AllowAny]  # Vacío temporalmente
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    def get_serializer_class(self):
        if self.action == 'create':
            return OrganizationCreateSerializer
        return OrganizationSerializer
    def get_authenticators(self):
        if self.request.method == 'POST':
            return []
        return super().get_authenticators()
    def get_permissions(self):
        print(f"========== ACTION: {self.action} ==========")  # Debug
        
        if self.action == 'create':  # POST = create
            print("========== ALLOW ANY ==========")
            return [AllowAny()]
        
        print("========== REQUIRE AUTH ==========")
        return [IsAuthenticated()]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Organization.objects.annotate(
                user_count = Count('users', filter=Q(users__is_active=True))
            ).select_related()
        return Organization.objects.filter(
            id=user.organization_id
        ).annotate(
            user_count=Count('users')
        )
    
    def retrieve(self, request, *args, **kwargs):
        """
        Cachear detalles de organización.
        """
        slug = kwargs.get('slug')
        cache_key = f'org_{slug}'

        data = cache.get(cache_key)
        if not data:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            data = serializer.data
            cache.set(cache_key, data, 300)
        return Response(data)

    @action(detail=True, methods=['post'], permission_classes=[IsOrganizationAdmin])
    def update_schema(self, request, slug):
        """
        Actualizar el schema de campos dinámicos para perfiles.
        """
        organization = self.get_object()
        serializer = OrganizationProfileSchemaSerializer(
            organization,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            #limpiar cache
            cache.delete(f'org_{slug}')
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, slug):
        """
        Retorna estadísticas de la organización.
        """
        organization = self.get_object()

        stats = {
            'total_users': organization.users.filter(is_active=True).count(),
            'active_today': organization.users.filter(last_login__date='today').count(),
            'profiles_completed': organization.users.filter(porfile__isnull=False).count()
        }

        return Response(stats)