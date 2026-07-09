from datetime import timedelta

from django.utils import timezone

from payments.advertising_packages import (
    TOURNAMENT_SPONSORSHIP_POSITIONS,
    get_classified_plan,
    get_sponsorship_plan,
    sponsorship_end_date,
)
from sports.models import AdvertisementBanner, Tournament

from .models import ClassifiedAdCampaign, TournamentSponsorship


def expire_stale_sponsorships():
    today = timezone.now().date()
    TournamentSponsorship.objects.filter(
        status="active", end_date__lt=today
    ).update(status="expired")


def get_active_sponsorship(tournament_id) -> TournamentSponsorship | None:
    expire_stale_sponsorships()
    today = timezone.now().date()
    return (
        TournamentSponsorship.objects.filter(
            tournament_id=tournament_id,
            status="active",
            start_date__lte=today,
            end_date__gte=today,
        )
        .select_related("tournament", "posted_by")
        .first()
    )


def create_sponsorship_banners(sponsorship: TournamentSponsorship):
    """Crea un banner por cada slot del ecosistema del torneo."""
    for position in TOURNAMENT_SPONSORSHIP_POSITIONS:
        AdvertisementBanner.objects.create(
            tournament=sponsorship.tournament,
            sponsorship=sponsorship,
            title=sponsorship.title,
            description=sponsorship.description,
            image=sponsorship.image,
            link_url=sponsorship.link_url,
            position=position,
            is_active=True,
            display_order=0,
            start_date=sponsorship.start_date,
            end_date=sponsorship.end_date,
            posted_by=sponsorship.posted_by,
        )


def deactivate_sponsorship_banners(sponsorship: TournamentSponsorship):
    AdvertisementBanner.objects.filter(sponsorship=sponsorship).update(is_active=False)


def build_sponsorship_availability(tournament: Tournament) -> dict:
    active = get_active_sponsorship(tournament.id)
    if active:
        return {
            "available": False,
            "tournament_id": str(tournament.id),
            "tournament_name": tournament.name,
            "tournament_status": tournament.status,
            "active_sponsorship": {
                "id": str(active.id),
                "title": active.title,
                "plan": active.plan,
                "plan_label": active.get_plan_display(),
                "start_date": active.start_date.isoformat(),
                "end_date": active.end_date.isoformat(),
                "days_remaining": active.days_remaining,
                "image": active.image,
                "link_url": active.link_url,
            },
            "days_remaining": active.days_remaining,
            "message": (
                f"Patrocinio activo hasta {active.end_date.strftime('%d/%m/%Y')}. "
                f"Quedan {active.days_remaining} día(s). "
                "¡Sé el siguiente patrocinador cuando expire!"
            ),
        }

    return {
        "available": True,
        "tournament_id": str(tournament.id),
        "tournament_name": tournament.name,
        "tournament_status": tournament.status,
        "active_sponsorship": None,
        "days_remaining": 0,
        "message": "Este torneo no tiene patrocinador exclusivo. ¡Oportunidad disponible!",
    }


def create_tournament_sponsorship(
    *,
    user,
    tournament: Tournament,
    plan_id: str,
    title: str,
    image: str,
    link_url: str = "",
    description: str = "",
) -> TournamentSponsorship:
    plan = get_sponsorship_plan(plan_id)
    if not plan:
        raise ValueError("Plan de patrocinio inválido.")

    if get_active_sponsorship(tournament.id):
        raise ValueError(
            "Este torneo ya tiene un patrocinio exclusivo activo. "
            "Espera a que expire o elige otro torneo."
        )

    today = timezone.now().date()
    end = sponsorship_end_date(today, plan_id)

    sponsorship = TournamentSponsorship.objects.create(
        tournament=tournament,
        posted_by=user,
        plan=plan_id,
        title=title,
        description=description,
        image=image,
        link_url=link_url,
        start_date=today,
        end_date=end,
        credits_spent=plan["credits"],
        status="active",
    )
    create_sponsorship_banners(sponsorship)
    return sponsorship


def expire_stale_campaigns():
    today = timezone.now().date()
    ClassifiedAdCampaign.objects.filter(
        status="active", end_date__lt=today
    ).update(status="expired")


def get_active_campaign_for_position(position: str, content_type: str = None):
    expire_stale_campaigns()
    today = timezone.now().date()
    qs = ClassifiedAdCampaign.objects.filter(
        position=position,
        status="active",
        start_date__lte=today,
        end_date__gte=today,
    )
    if content_type:
        qs = qs.filter(content_type=content_type)
    return qs.order_by("-created_at").first()


def create_classified_campaign(
    *,
    user,
    content_type: str,
    content_object,
    plan_id: str,
    position: str,
    title: str,
    image: str,
    link_url: str = "",
    description: str = "",
) -> ClassifiedAdCampaign:
    from django.contrib.contenttypes.models import ContentType

    plan = get_classified_plan(plan_id)
    if not plan:
        raise ValueError("Plan publicitario inválido.")

    today = timezone.now().date()
    end = today + timedelta(days=plan["days"])

    ct = ContentType.objects.get_for_model(content_object)
    campaign = ClassifiedAdCampaign.objects.create(
        posted_by=user,
        content_type=content_type,
        content_type_ref=ct,
        object_id=content_object.pk,
        plan=plan_id,
        position=position,
        title=title,
        description=description,
        image=image,
        link_url=link_url,
        target_reach=plan["target_reach"],
        frequency_cap=plan["frequency_cap"],
        start_date=today,
        end_date=end,
        credits_spent=plan["credits"],
        status="active",
    )

    AdvertisementBanner.objects.create(
        campaign=campaign,
        title=title,
        description=description,
        image=image,
        link_url=link_url,
        position=position,
        is_active=True,
        display_order=0,
        start_date=today,
        end_date=end,
        posted_by=user,
    )
    return campaign


def record_campaign_impression(campaign: ClassifiedAdCampaign, viewer_hash: str) -> bool:
    """
    Registra impresión respetando frequency cap y target reach.
    Retorna True si se sirvió la impresión.
    """
    from .models import AdViewerImpression

    if not campaign.is_active_now:
        return False

    if campaign.unique_views >= campaign.target_reach:
        campaign.status = "completed"
        campaign.save(update_fields=["status", "updated_at"])
        return False

    if campaign.total_impressions >= campaign.max_impressions:
        campaign.status = "completed"
        campaign.save(update_fields=["status", "updated_at"])
        return False

    record, created = AdViewerImpression.objects.get_or_create(
        campaign=campaign,
        viewer_hash=viewer_hash,
        defaults={"impression_count": 1},
    )

    if not created:
        if record.impression_count >= campaign.frequency_cap:
            return False
        record.impression_count += 1
        record.save(update_fields=["impression_count", "updated_at"])
    else:
        campaign.unique_views += 1

    campaign.total_impressions += 1
    update_fields = ["total_impressions", "updated_at"]
    if created:
        update_fields.append("unique_views")
    if campaign.unique_views >= campaign.target_reach:
        campaign.status = "completed"
        update_fields.append("status")
    campaign.save(update_fields=update_fields)
    return True
