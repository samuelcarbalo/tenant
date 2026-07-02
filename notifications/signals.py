from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from jobs.models import JobApplication

from .services import notify_job_status_change


@receiver(pre_save, sender=JobApplication)
def cache_application_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._prev_status = JobApplication.objects.values_list("status", flat=True).get(pk=instance.pk)
        except JobApplication.DoesNotExist:
            instance._prev_status = None
    else:
        instance._prev_status = None


@receiver(post_save, sender=JobApplication)
def notify_application_status_change(sender, instance, created, **kwargs):
    if created:
        return
    prev = getattr(instance, "_prev_status", None)
    if prev and prev != instance.status:
        notify_job_status_change(application=instance)
