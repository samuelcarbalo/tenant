import logging

from django.contrib.contenttypes.models import ContentType

from jobs.models import JobOffer
from moderation.models import ReportePublicacion
from real_estate.models import RealEstateOffer
from sports.models import Tournament

logger = logging.getLogger(__name__)

from events.models import EventListing

CONTENT_TYPE_MAP = {
    "job": JobOffer,
    "real_estate": RealEstateOffer,
    "tournament": Tournament,
    "event": EventListing,
}


def get_content_type_for_model(model_class):
    return ContentType.objects.get_for_model(model_class)


def apply_moderation_if_needed(content_type, object_id):
    """Si hay >= 3 reportes, oculta la publicación (pendiente_revision)."""
    count = ReportePublicacion.objects.filter(
        content_type=content_type,
        object_id=object_id,
    ).count()

    if count < ReportePublicacion.REPORT_THRESHOLD:
        return

    model = content_type.model_class()
    try:
        obj = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        return

    if hasattr(obj, "moderation_status"):
        obj.moderation_status = "pendiente_revision"
        update_fields = ["moderation_status"]
        if hasattr(obj, "is_active"):
            obj.is_active = False
            update_fields.append("is_active")
        obj.save(update_fields=update_fields)
        logger.warning(
            "Publication %s %s hidden pending review (%s reports)",
            content_type.model,
            object_id,
            count,
        )
