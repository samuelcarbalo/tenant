from rest_framework import serializers

from .models import EventListing


class EventListingListSerializer(serializers.ModelSerializer):
    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    category_label = serializers.CharField(
        source="get_event_category_display", read_only=True
    )

    class Meta:
        model = EventListing
        fields = [
            "id",
            "title",
            "slug",
            "event_category",
            "category_label",
            "start_datetime",
            "end_datetime",
            "location",
            "is_online",
            "cover_image",
            "organizer_name",
            "price_info",
            "posted_at",
            "expires_at",
            "days_remaining",
            "is_expired",
            "is_active",
            "views_count",
        ]


class EventListingDetailSerializer(serializers.ModelSerializer):
    days_remaining = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    category_label = serializers.CharField(
        source="get_event_category_display", read_only=True
    )

    class Meta:
        model = EventListing
        fields = "__all__"


class EventListingCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventListing
        fields = [
            "id",
            "title",
            "description",
            "event_category",
            "start_datetime",
            "end_datetime",
            "location",
            "address",
            "is_online",
            "online_url",
            "cover_image",
            "organizer_name",
            "contact_phone",
            "contact_email",
            "external_link",
            "price_info",
            "is_active",
        ]

    def validate(self, data):
        start = data.get("start_datetime")
        end = data.get("end_datetime")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_datetime": "La fecha de fin debe ser posterior al inicio."}
            )
        return data
