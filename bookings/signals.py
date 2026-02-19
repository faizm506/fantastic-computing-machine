from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile, Company

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Assign to the first available company by default
        default_company = Company.objects.first()
        if default_company:
            Profile.objects.get_or_create(user=instance, company=default_company)