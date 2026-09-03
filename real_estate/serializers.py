from rest_framework import serializers
from .models import RealEstateOffer


def _image_src(obj):
    return obj.public_image_url or None


class RealEstateOfferListSerializer(serializers.ModelSerializer):
    """
    Serializer para listado de ofertas de bienes raíces (campos esenciales públicos).
    """

    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    posted_by_name = serializers.CharField(source="posted_by.full_name", read_only=True)
    posted_by = serializers.UUIDField(source="posted_by_id", read_only=True)
    image = serializers.SerializerMethodField()

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

    def get_image(self, obj):
        return _image_src(obj)


class RealEstateOfferDetailSerializer(serializers.ModelSerializer):
    """
    Serializer para detalle completo de una propiedad de bienes raíces.
    """

    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    posted_by_name = serializers.CharField(source="posted_by.full_name", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = RealEstateOffer
        fields = "__all__"

    def get_image(self, obj):
        return _image_src(obj)


class RealEstateOfferCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para crear o actualizar una oferta de bienes raíces (solo managers).
    `image` acepta una URL HTTPS (archivo subido en el cliente o enlace externo).
    """

    image = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=500,
    )

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

    def validate_image(self, value):
        if value is None:
            return ""
        url = str(value).strip()
        if not url:
            return ""
        if not (url.startswith("http://") or url.startswith("https://")):
            raise serializers.ValidationError(
                "La imagen debe ser una URL http(s) válida."
            )
        return url

    def create(self, validated_data):
        url = validated_data.pop("image", "") or ""
        return super().create({**validated_data, "image_url": url})

    def update(self, instance, validated_data):
        if "image" in validated_data:
            instance.image_url = validated_data.pop("image") or ""
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["image"] = _image_src(instance)
        return data
