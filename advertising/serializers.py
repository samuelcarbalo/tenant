from rest_framework import serializers

from payments.advertising_packages import (
    CLASSIFIED_AD_PLANS,
    CLASSIFIED_POSITIONS,
    SPONSORSHIP_PLANS,
)
from sports.models import Tournament

from .models import ClassifiedAdCampaign, TournamentSponsorship


class SponsorshipPlanSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    credits = serializers.IntegerField()
    days = serializers.IntegerField()
    description = serializers.CharField()


class ClassifiedPlanSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    credits = serializers.IntegerField()
    target_reach = serializers.IntegerField()
    frequency_cap = serializers.IntegerField()
    days = serializers.IntegerField()
    description = serializers.CharField()


class TournamentSponsorshipSerializer(serializers.ModelSerializer):
    plan_label = serializers.CharField(source="get_plan_display", read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    is_active_now = serializers.BooleanField(read_only=True)
    tournament_name = serializers.CharField(source="tournament.name", read_only=True)
    tournament_slug = serializers.CharField(source="tournament.slug", read_only=True)

    class Meta:
        model = TournamentSponsorship
        fields = [
            "id",
            "tournament",
            "tournament_name",
            "tournament_slug",
            "posted_by",
            "plan",
            "plan_label",
            "title",
            "description",
            "image",
            "link_url",
            "start_date",
            "end_date",
            "credits_spent",
            "status",
            "days_remaining",
            "is_active_now",
            "created_at",
        ]
        read_only_fields = [
            "posted_by",
            "start_date",
            "end_date",
            "credits_spent",
            "status",
            "created_at",
        ]


class TournamentSponsorshipCreateSerializer(serializers.Serializer):
    tournament = serializers.PrimaryKeyRelatedField(queryset=Tournament.objects.all())
    plan = serializers.ChoiceField(choices=list(SPONSORSHIP_PLANS.keys()))
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    image = serializers.URLField()
    link_url = serializers.URLField(required=False, allow_blank=True, default="")


class ClassifiedAdCampaignSerializer(serializers.ModelSerializer):
    days_remaining = serializers.IntegerField(read_only=True)
    is_active_now = serializers.BooleanField(read_only=True)
    max_impressions = serializers.IntegerField(read_only=True)
    content_type_label = serializers.CharField(
        source="get_content_type_display", read_only=True
    )

    class Meta:
        model = ClassifiedAdCampaign
        fields = [
            "id",
            "posted_by",
            "content_type",
            "content_type_label",
            "object_id",
            "plan",
            "position",
            "title",
            "description",
            "image",
            "link_url",
            "target_reach",
            "frequency_cap",
            "unique_views",
            "total_impressions",
            "max_impressions",
            "start_date",
            "end_date",
            "credits_spent",
            "status",
            "days_remaining",
            "is_active_now",
            "created_at",
        ]
        read_only_fields = [
            "posted_by",
            "target_reach",
            "frequency_cap",
            "unique_views",
            "total_impressions",
            "start_date",
            "end_date",
            "credits_spent",
            "status",
            "created_at",
        ]


class ClassifiedAdCampaignCreateSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=["job", "real_estate", "event"])
    object_id = serializers.UUIDField()
    plan = serializers.ChoiceField(choices=list(CLASSIFIED_AD_PLANS.keys()))
    position = serializers.CharField(max_length=30)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    image = serializers.URLField()
    link_url = serializers.URLField(required=False, allow_blank=True, default="")

    def validate(self, data):
        content_type = data["content_type"]
        position = data["position"]
        allowed = {p[0] for p in CLASSIFIED_POSITIONS.get(content_type, [])}
        if position not in allowed:
            raise serializers.ValidationError(
                {
                    "position": f"Posición inválida para {content_type}. "
                    f"Opciones: {', '.join(sorted(allowed))}"
                }
            )
        return data
