from rest_framework import serializers
# from django.utils import timezone

from .models import JobOffer, JobApplication, JobOfferHistory


class JobOfferListSerializer(serializers.ModelSerializer):
    """Serializer para listado de ofertas (campos públicos)"""

    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    posted_by_name = serializers.CharField(source="posted_by.full_name", read_only=True)

    class Meta:
        model = JobOffer
        fields = [
            "id",
            "title",
            "company_name",
            "location",
            "remote",
            "job_type",
            "category",  # ← AGREGAR
            "salary_min",
            "salary_max",
            "currency",
            "skills",
            "posted_at",
            "expires_at",
            "days_remaining",
            "is_expired",
            "is_active",
            "applications_count",
            "posted_by_name",
            "views_count",
            "is_external",
            "external_apply_url",
        ]


class JobOfferDetailSerializer(serializers.ModelSerializer):
    """Serializer para detalle de oferta"""

    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    can_apply = serializers.SerializerMethodField()
    has_applied = serializers.SerializerMethodField()

    class Meta:
        model = JobOffer
        fields = "__all__"

    def get_can_apply(self, obj):
        """Verificar si el usuario puede postularse"""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False

        # No puede postularse si ya aplicó
        if JobApplication.objects.filter(offer=obj, applicant=request.user).exists():
            return False

        # No puede postularse si la oferta expiró
        if obj.is_expired:
            return False

        return True

    def get_has_applied(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            # Usamos .id o .pk para asegurar que pasamos el UUID y no el objeto User completo
            user_id = request.user.pk
            return obj.applications.filter(applicant_id=user_id).exists()
        return False


class JobOfferCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer para crear/editar ofertas (solo managers)"""

    # EXPLÍCITAMENTE opcional
    company_name = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    expires_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        input_formats=["iso-8601", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"],
    )

    class Meta:
        model = JobOffer
        fields = [
            "id",
            "title",
            "company_name",
            "description",
            "requirements",
            "location",
            "remote",
            "job_type",
            "category",  # ← AGREGAR
            "benefits",  # ← AGREGAR
            "salary_min",
            "salary_max",
            "currency",
            "skills",
            "is_featured",
            "is_external",
            "external_apply_url",
            "expires_at",
        ]
        # Opcional: excluir company_name de los campos requeridos
        extra_kwargs = {
            "id": {"read_only": True},  # ← Solo lectura, se genera automáticamente
            "company_name": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },
            "category": {"required": False, "allow_blank": True},
            "benefits": {"required": False},
            "is_external": {"required": False},
            "external_apply_url": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },
            "expires_at": {"required": False},
        }

    def validate_skills(self, value):
        """Validar que skills sea una lista de strings"""
        if not isinstance(value, list):
            raise serializers.ValidationError("Skills debe ser una lista.")
        if not all(isinstance(s, str) for s in value):
            raise serializers.ValidationError("Cada skill debe ser un texto.")
        return value

    def validate(self, data):
        """Validación general: asignar company_name si no viene; URL externa obligatoria."""
        if not data.get("company_name"):
            data["company_name"] = ""
        if not data.get("expires_at"):
            data.pop("expires_at", None)
        is_external = data.get("is_external")
        if is_external is None and self.instance is not None:
            is_external = self.instance.is_external
        url = data.get("external_apply_url")
        if url is None and self.instance is not None:
            url = self.instance.external_apply_url
        if is_external and not url:
            raise serializers.ValidationError(
                {
                    "external_apply_url": (
                        "La URL de postulación es obligatoria para ofertas externas."
                    )
                }
            )
        if is_external is False:
            data["external_apply_url"] = None
        return data


class JobApplicationSerializer(serializers.ModelSerializer):
    """Serializer para postulaciones"""

    applicant_name = serializers.CharField(source="applicant.full_name", read_only=True)
    applicant_email = serializers.CharField(source="applicant.email", read_only=True)
    offer_title = serializers.CharField(source="offer.title", read_only=True)
    company_name = serializers.CharField(source="offer.company_name", read_only=True)
    application_count = serializers.IntegerField(
        source="offer.applications_count", read_only=True
    )
    views_count = serializers.IntegerField(source="offer.views_count", read_only=True)
    location = serializers.CharField(source="offer.location", read_only=True)
    offer_id = serializers.UUIDField(source="offer.pk", read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            "id",
            "offer_title",
            "applicant",
            "applicant_name",
            "company_name",
            "location",
            "offer_id",
            "applicant_email",
            "application_count",
            "cv_file",
            "views_count",
            "cover_letter",
            "status",
            "recruiter_notes",
            "applied_at",
        ]
        read_only_fields = [
            "id",
            "offer",
            "applicant",
            "status",
            "recruiter_notes",
            "applied_at",
        ]
        extra_kwargs = {
            "cv_file": {"required": False, "allow_null": True},
            "cover_letter": {"required": False, "allow_blank": True},
        }

    def validate_csv_file(self, value):
        """Validar que el CV no exceda 1MB"""
        if value.size > 1024 * 1024:  # 1MB
            raise serializers.ValidationError("El archivo no puede exceder 1MB.")
        if not value.name.endswith(".pdf"):
            raise serializers.ValidationError("El archivo debe ser un PDF.")
        return value

    def validate(self, data):
        """Validar que la oferta esté activa y no expirada"""
        offer = data.get("offer")
        # Si offer no viene en data, se asignará desde el viewset
        if not offer:
            return data
        if offer.is_expired:
            raise serializers.ValidationError("Esta oferta ha expirado.")
        if not offer.is_active:
            raise serializers.ValidationError("Esta oferta no está activa.")
        # Verificar que el usuario no haya postulado ya
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            if JobApplication.objects.filter(
                offer=offer, applicant=request.user
            ).exists():
                raise serializers.ValidationError("Ya te has postulado a esta oferta.")
        return data


class JobApplicationUpdateSerializer(serializers.ModelSerializer):
    """Serializer para que reclutadores actualicen postulaciones"""

    class Meta:
        model = JobApplication
        fields = ["status", "recruiter_notes"]


class JobOfferHistorySerializer(serializers.ModelSerializer):
    published_by_name = serializers.CharField(
        source="published_by.full_name", read_only=True, default=""
    )
    published_by_email = serializers.CharField(
        source="published_by.email", read_only=True, default=""
    )
    offer_type = serializers.SerializerMethodField()

    class Meta:
        model = JobOfferHistory
        fields = [
            "id",
            "original_job_id",
            "title",
            "company_name",
            "published_by",
            "published_by_name",
            "published_by_email",
            "created_at",
            "expired_at",
            "is_external",
            "offer_type",
            "external_apply_url",
            "total_applications_count",
            "metadata",
            "is_purged",
            "recorded_at",
        ]

    def get_offer_type(self, obj):
        return "Externa" if obj.is_external else "Interna"
