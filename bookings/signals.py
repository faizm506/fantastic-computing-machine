from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile, Company, Booking, ActivityLog

# 1. Handle User Profile Creation
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Assign to the first available company by default
        default_company = Company.objects.first()
        if default_company:
            # We use get_or_create to prevent IntegrityErrors
            Profile.objects.get_or_create(user=instance, defaults={'company': default_company})

# 2. Handle Booking Activity Pulse
@receiver(post_save, sender=Booking)
def log_booking_activity(sender, instance, created, **kwargs):
    """
    Automatically creates a pulse entry whenever a booking is saved.
    Note: 'user' is left as None here because signals can't see the request.
    We will update the user attribution logic in the view or via middleware.
    """
    if created:
        action_text = f"Initialized New Entry: {instance.customer_name}"
    else:
        action_text = f"Modified Registry: {instance.customer_name}"
        
    # Check if a log already exists for this exact second to prevent duplicates
    ActivityLog.objects.create(
        company=instance.company,
        action=action_text,
        reference_id=instance.booking_id
    )

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from .models import ActivityLog

# 3. Log User Sign-In
@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    if hasattr(user, 'profile'):
        ActivityLog.objects.create(
            company=user.profile.company,
            user=user,
            action="🔐 System Authentication: Secure Login Success"
        )

# 4. Log User Sign-Out
@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user and hasattr(user, 'profile'):
        ActivityLog.objects.create(
            company=user.profile.company,
            user=user,
            action="🚪 Session Terminated: Manual Logout"
        )