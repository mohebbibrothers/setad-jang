"""
Signal handlers for authentication model lifecycle events.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, User


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """ساخت خودکار profile موقع ساخت user."""
    if created:
        Profile.objects.create(user=instance)
