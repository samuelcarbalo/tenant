from rest_framework import serializers
from .models import RealEstateOffer


class RealEstateOfferListSerializer(serializers.ModelSerializer):
    """
    Serializer para listado de ofertas de bienes raíces (campos esenciales públicos).
    """

    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    posted_by_name = serializers.CharField(source="posted_by.full_name", read_only=True)
    posted_by = serializers.UUIDField(source="posted_by_id", read_only=True)

    class Meta:
        model = RealEstateOffer
        fields = [
            "id",
            "title",
            "price",
            "currency",
            "image",
            "location",
            "category",
            "property_type",
            "posted_at",
            "expires_at",
            "days_remaining",
            "is_expired",
            "is_active",
            "is_featured",
            "posted_by_name",
            "posted_by",
            "views_count",
        ]


class RealEstateOfferDetailSerializer(serializers.ModelSerializer):
    """
    Serializer para detalle completo de una propiedad de bienes raíces.
    """

    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    posted_by_name = serializers.CharField(source="posted_by.full_name", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = RealEstateOffer
        fields = "__all__"


class RealEstateOfferCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para crear o actualizar una oferta de bienes raíces (solo managers).
    """

    class Meta:
        model = RealEstateOffer
        fields = [
            "title",
            "description",
            "price",
            "currency",
            "image",
            "location",
            "category",
            "property_type",
            "contact_name",
            "contact_phone",
            "contact_email",
            "is_featured",
        ]

    def validate_price(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a cero.")
        return value
