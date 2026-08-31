"""Servicios de historial analítico y depuración de vacantes caducadas."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone


def build_job_metadata(offer) -> dict:
    salary: dict[str, str] = {}
    if offer.salary_min is not None:
        salary["min"] = str(offer.salary_min)
    if offer.salary_max is not None:
        salary["max"] = str(offer.salary_max)
    if offer.currency:
        salary["currency"] = offer.currency
    return {
        "category": offer.category or "",
        "location": offer.location or "",
        "salary": salary,
        "job_type": getattr(offer, "job_type", ""),
        "remote": bool(getattr(offer, "remote", False)),
        "views_count": getattr(offer, "views_count", 0),
        "moderation_status": getattr(offer, "moderation_status", ""),
        "organization_id": str(offer.organization_id) if offer.organization_id else None,
    }


def upsert_job_offer_history(offer, *, is_purged: bool = False, expired_at=None):
    from .models import JobOfferHistory

    defaults = {
        "title": offer.title,
        "company_name": offer.company_name,
        "published_by": offer.posted_by,
        "created_at": offer.created_at or timezone.now(),
        "expired_at": expired_at if expired_at is not None else offer.expires_at,
        "is_external": bool(getattr(offer, "is_external", False)),
        "external_apply_url": getattr(offer, "external_apply_url", None) or None,
        "total_applications_count": offer.applications_count or 0,
        "metadata": build_job_metadata(offer),
    }
    if is_purged:
        defaults["is_purged"] = True

    history, _created = JobOfferHistory.objects.update_or_create(
        original_job_id=offer.id,
        defaults=defaults,
    )
    return history


def sync_all_job_offers_to_history() -> int:
    from .models import JobOffer

    synced = 0
    qs = JobOffer.objects.select_related("posted_by", "organization")
    for offer in qs.iterator(chunk_size=200):
        upsert_job_offer_history(offer)
        synced += 1
    return synced


def purge_expired_job_offers() -> dict[str, int]:
    """
    Consolida métricas en JobOfferHistory y elimina JobOffer caducadas.
    """
    from .models import JobOffer

    now = timezone.now()
    expired_ids = list(
        JobOffer.objects.filter(expires_at__lte=now).values_list("id", flat=True)
    )
    purged = 0
    with transaction.atomic():
        offers = JobOffer.objects.filter(id__in=expired_ids).select_related(
            "posted_by", "organization"
        )
        for offer in offers:
            upsert_job_offer_history(
                offer, is_purged=True, expired_at=offer.expires_at
            )
            offer.delete()
            purged += 1
    return {"purged": purged, "candidates": len(expired_ids)}
