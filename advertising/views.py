from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from authentication.models import User
from jobs.models import JobOffer
from payments.advertising_packages import (
    CLASSIFIED_AD_PLANS,
    CLASSIFIED_POSITIONS,
    SPONSORSHIP_PLANS,
)
from real_estate.models import RealEstateOffer
from sports.models import Tournament

from .models import ClassifiedAdCampaign, TournamentSponsorship
from .serializers import (
    ClassifiedAdCampaignCreateSerializer,
    ClassifiedAdCampaignSerializer,
    ClassifiedPlanSerializer,
    SponsorshipPlanSerializer,
    TournamentSponsorshipCreateSerializer,
    TournamentSponsorshipSerializer,
)
from .services import (
    build_sponsorship_availability,
    create_classified_campaign,
    create_tournament_sponsorship,
    get_active_sponsorship,
    record_campaign_impression,
)


class TournamentSponsorshipViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Patrocinios exclusivos de torneos.
    - GET list/retrieve: público
    - POST purchase: autenticado, descuenta créditos
    """

    queryset = TournamentSponsorship.objects.select_related("tournament", "posted_by")
    serializer_class = TournamentSponsorshipSerializer

    def get_permissions(self):
        if self.action in ["purchase", "my_sponsorships"]:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_queryset(self):
        qs = super().get_queryset()
        tournament_id = self.request.query_params.get("tournament")
        if tournament_id:
            qs = qs.filter(tournament_id=tournament_id)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def plans(self, request):
        data = SponsorshipPlanSerializer(SPONSORSHIP_PLANS.values(), many=True).data
        return Response(data)

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def availability(self, request):
        tournament_id = request.query_params.get("tournament")
        slug = request.query_params.get("slug")
        if not tournament_id and not slug:
            return Response(
                {"error": "Indica tournament (id) o slug."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if slug:
                tournament = Tournament.objects.get(slug=slug)
            else:
                tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            return Response(
                {"error": "Torneo no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(build_sponsorship_availability(tournament))

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_sponsorships(self, request):
        qs = self.get_queryset().filter(posted_by=request.user)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def purchase(self, request):
        serializer = TournamentSponsorshipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = SPONSORSHIP_PLANS[data["plan"]]
        user = request.user

        with transaction.atomic():
            fresh_user = User.objects.select_for_update().get(id=user.id)
            if fresh_user.credits < plan["credits"]:
                raise ValidationError(
                    {
                        "detail": (
                            f"Necesitas {plan['credits']} créditos para el plan "
                            f"{plan['label']}. Tienes {fresh_user.credits}."
                        )
                    }
                )

            try:
                sponsorship = create_tournament_sponsorship(
                    user=fresh_user,
                    tournament=data["tournament"],
                    plan_id=data["plan"],
                    title=data["title"],
                    image=data["image"],
                    link_url=data.get("link_url", ""),
                    description=data.get("description", ""),
                )
            except ValueError as exc:
                raise ValidationError({"detail": str(exc)}) from exc

            fresh_user.credits -= plan["credits"]
            fresh_user.save(update_fields=["credits"])
            user.credits = fresh_user.credits

        out = TournamentSponsorshipSerializer(sponsorship).data
        out["credits_remaining"] = user.credits
        return Response(out, status=status.HTTP_201_CREATED)


class ClassifiedAdCampaignViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ClassifiedAdCampaign.objects.select_related("posted_by")
    serializer_class = ClassifiedAdCampaignSerializer

    def get_permissions(self):
        if self.action == "record_impression":
            return [AllowAny()]
        if self.action in ["purchase", "my_campaigns"]:
            return [IsAuthenticated()]
        return [AllowAny()]

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def plans(self, request):
        data = ClassifiedPlanSerializer(CLASSIFIED_AD_PLANS.values(), many=True).data
        return Response(data)

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def positions(self, request):
        content_type = request.query_params.get("content_type", "job")
        positions = [
            {"value": value, "label": label}
            for value, label in CLASSIFIED_POSITIONS.get(content_type, [])
        ]
        return Response(positions)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_campaigns(self, request):
        qs = self.get_queryset().filter(posted_by=request.user)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def purchase(self, request):
        serializer = ClassifiedAdCampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = CLASSIFIED_AD_PLANS[data["plan"]]
        user = request.user

        content_object = self._resolve_content_object(
            data["content_type"], data["object_id"], user
        )

        with transaction.atomic():
            fresh_user = User.objects.select_for_update().get(id=user.id)
            if fresh_user.credits < plan["credits"]:
                raise ValidationError(
                    {
                        "detail": (
                            f"Necesitas {plan['credits']} créditos. "
                            f"Tienes {fresh_user.credits}."
                        )
                    }
                )

            try:
                campaign = create_classified_campaign(
                    user=fresh_user,
                    content_type=data["content_type"],
                    content_object=content_object,
                    plan_id=data["plan"],
                    position=data["position"],
                    title=data["title"],
                    image=data["image"],
                    link_url=data.get("link_url", ""),
                    description=data.get("description", ""),
                )
            except ValueError as exc:
                raise ValidationError({"detail": str(exc)}) from exc

            fresh_user.credits -= plan["credits"]
            fresh_user.save(update_fields=["credits"])
            user.credits = fresh_user.credits

        out = ClassifiedAdCampaignSerializer(campaign).data
        out["credits_remaining"] = user.credits
        return Response(out, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[AllowAny])
    def record_impression(self, request, pk=None):
        campaign = self.get_object()
        viewer_hash = request.data.get("viewer_hash") or request.query_params.get(
            "viewer_hash"
        )
        if not viewer_hash:
            return Response(
                {"error": "viewer_hash es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        served = record_campaign_impression(campaign, viewer_hash[:64])
        campaign.refresh_from_db()
        return Response(
            {
                "served": served,
                "unique_views": campaign.unique_views,
                "total_impressions": campaign.total_impressions,
                "target_reach": campaign.target_reach,
                "status": campaign.status,
            }
        )

    def _resolve_content_object(self, content_type: str, object_id, user):
        if content_type == "job":
            obj = JobOffer.objects.filter(id=object_id).first()
            if not obj or obj.posted_by_id != user.id:
                raise ValidationError({"object_id": "Oferta de empleo no encontrada."})
            return obj
        if content_type == "real_estate":
            obj = RealEstateOffer.objects.filter(id=object_id).first()
            if not obj or obj.posted_by_id != user.id:
                raise ValidationError({"object_id": "Publicación inmobiliaria no encontrada."})
            return obj
        if content_type == "event":
            from events.models import EventListing

            obj = EventListing.objects.filter(id=object_id).first()
            if not obj or obj.posted_by_id != user.id:
                raise ValidationError({"object_id": "Evento no encontrado."})
            return obj
        raise ValidationError({"content_type": "Tipo de contenido inválido."})
