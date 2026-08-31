from django.db.models.signals import post_save
from django.dispatch import receiver

from jobs.models import JobApplication

from .services import create_job_application_conversation


@receiver(post_save, sender=JobApplication)
def auto_create_job_conversation(sender, instance, created, **kwargs):
    """Crea conversación automática al postularse a una oferta laboral."""
    if created and instance.status != "redirected":
        create_job_application_conversation(instance)
