from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import MedicalProfile, ProfileAnalytics

@receiver(post_save, sender=MedicalProfile)
def create_profile_analytics(sender, instance, created, **kwargs):
    if created:
        ProfileAnalytics.objects.create(profile=instance)