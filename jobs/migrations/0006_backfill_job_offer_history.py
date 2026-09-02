from django.db import migrations


def backfill_history(apps, schema_editor):
    JobOffer = apps.get_model("jobs", "JobOffer")
    JobOfferHistory = apps.get_model("jobs", "JobOfferHistory")
    for offer in JobOffer.objects.all().iterator(chunk_size=200):
        salary = {}
        if offer.salary_min is not None:
            salary["min"] = str(offer.salary_min)
        if offer.salary_max is not None:
            salary["max"] = str(offer.salary_max)
        if offer.currency:
            salary["currency"] = offer.currency
        JobOfferHistory.objects.update_or_create(
            original_job_id=offer.id,
            defaults={
                "title": offer.title,
                "company_name": offer.company_name,
                "published_by_id": offer.posted_by_id,
                "created_at": offer.created_at,
                "expired_at": offer.expires_at,
                "is_external": bool(getattr(offer, "is_external", False)),
                "external_apply_url": getattr(offer, "external_apply_url", None),
                "total_applications_count": offer.applications_count or 0,
                "metadata": {
                    "category": offer.category or "",
                    "location": offer.location or "",
                    "salary": salary,
                    "job_type": offer.job_type,
                    "remote": bool(offer.remote),
                    "views_count": offer.views_count,
                },
                "is_purged": False,
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0005_joboffer_external_and_history"),
    ]

    operations = [
        migrations.RunPython(backfill_history, noop),
    ]
