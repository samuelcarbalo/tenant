from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Prefetch
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from .models import Profile
from .serializers import (
    ProfileSerializer,
    ProfileCreateUpdateSerializer,
    ProfileListSerializer,
    ProfileSearchSerializer
)
from core.permissions import IsOrganizationMember, IsOrganizationAdmin
from core.pagination import StandardResultsSetPagination

class ProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestión de perfiles con optimizaciones de query.
    """
    pagination_class =  StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'department']
    ordering_fields = ['created_at', 'completion_percentage', 'user__email']
    lookup_field = 'pk'

    def get_queryset(self):
        """
        Optimización: Siempre filtrar por organización y usar select_related.
        """
        user = self.request.user
        
        queryset = Profile.objects.select_related(
            'user', 'organization'
        ).only(
            'id', 'user__id', 'user__email', 'user__first_name', 
            'user__last_name', 'organization__id', 'organization__name',
            'bio', 'birth_date', 'location', 'department', 'job_title',
            'dynamic_data', 'avatar', 'completion_percentage',
            'created_at', 'updated_at'
        )
        # Filtrado multi-tenant
        if user.is_superuser:
            # Superusers pueden ver todas o filtrar por org
            org_id = self.request.query_params.get('organization')
            if org_id:
                queryset = queryset.filter(organization_id=org_id)
        else:
            # Usuarios normales solo ven su organización
            queryset = queryset.filter(organization=user.organization)

        department = self.request.query_params.get('department')
        if department:
            queryset = queryset.filter(department__icontains = department)

        completion = self.request.query_params.get('completion_min')
        if completion:
            queryset = queryset.filter(completion_percentage__gte=completion)
        
        return queryset.order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProfileCreateUpdateSerializer
        elif self.action == 'list':
            return ProfileListSerializer
        return ProfileSerializer


    def get_object(self):
        """
        Cachear objetos individuales.
        """
        pk = self.kwargs.get('pk')
        cache_key = f'profile_{pk}'

        obj = cache.get(cache_key)
        if not obj:
            obj = super().get_object()
            cache.set(cache_key, obj, 300)        
        return obj
    
    def perform_update(self, serializer):
        super().perform_update(serializer)
        cache.delete(f'profile_{serializer.instance.id}')

    def perform_destroy(self, instance):
        cache.delete(f'profile_{instance.id}')
        super().perform_destroy(instance)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """
        Obtener perfil del usuario autenticado.
        """
        try:
            profile =  Profile.objects.select_related('user', 'organization').get(user=request.user)
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
        except Profile.DoesNotExist:
            return Response(
                {'error': 'Perfil no encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Búsqueda avanzada de perfiles.
        """
        serializer = ProfileSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query = serializer.validated_data['query']
        department = serializer.validated_data.get('department')
        fields = serializer.validated_data.get('fields', [])

        # Construir query optimizada
        queryset = self.get_queryset()

        # Búsqueda en múltiples campos
        search_filter = (
            Q(user__email__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(department__icontains=query) |
            Q(job_title__icontains=query) |
            Q(dynamic_data__icontains=query) # PostgreSQL JSON search
        )

        queryset = queryset.filter(search_filter)

        if department:
            queryset = queryset.filter(department__icontains=department)

        # Paginar resultados
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsOrganizationAdmin])
    def update_dynamic_field(self, request, pk=None):
        """
        Actualizar un campo dinámico específico (admin only).
        """
        profile = self.get_object()
        field_name = request.data.get('field_name')
        field_value = request.data.get('field_value')

        if not field_name or not field_value:
            return Response(
                {'error': 'field_name y field_value son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar que el campo existe en el schema
        allowed_fields = {f['name'] for f in profile.organization.get_profile_fields()}
        if field_name not in allowed_fields:
            return Response(
                {'error': f'Campo {field_name} no permitido.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Actualizar campo dinámico
        dynamic_data = profile.dynamic_data or {}
        dynamic_data[field_name] = field_value
        profile.dynamic_data = dynamic_data
        profile.save()

        return Response(ProfileSerializer(profile).data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Estadísticas de perfiles en la organización.
        """
        from django.db.models import Count, Avg
        
        queryset = self.get_queryset()
        stats = {
            'total_profiles': queryset.count(),
            'by_department': list(
                queryset.values('department')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
            'avg_completion': queryset.aggregate(
                avg=Avg('completion_percentage')
            )['avg'] or 0,
            'completed_profiles': queryset.filter(
                completion_percentage=100
            ).count(),
            
        }
        
        return Response(stats)

    @action(detail=False, methods=['get'])
    def schema(self, request):
        """
        Obtener el schema de campos dinámicos de la organización.
        """
        organization = request.user.organization
        if not organization:
            return Response(
                {'error': 'Usuario sin organización asignada.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response({
            'organization': organization.name,
            'fields': organization.get_profile_fields()
        })
    