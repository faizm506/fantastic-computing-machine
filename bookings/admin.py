from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import mark_safe
from .models import Company, Profile, Booking

# --- 1. COMPANY ADMIN (The Command Center) ---
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'id_prefix', 'logo_preview', 'manager_count')
    search_fields = ('name', 'id_prefix')
    list_per_page = 20

    def logo_preview(self, obj):
        if obj.logo:
            return mark_safe(f'<img src="{obj.logo.url}" style="height: 30px; border-radius: 5px; border: 1px solid #ccc;" />')
        return "-"
    logo_preview.short_description = "Brand Identity"

    def manager_count(self, obj):
        count = Profile.objects.filter(company=obj).count()
        return f"{count} Active"
    manager_count.short_description = "Managers"

# --- 2. USER ADMIN (With Company Link) ---
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Company Association'
    fk_name = 'user'

class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'get_company', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'profile__company') # Filter users by Company!
    
    def get_company(self, instance):
        return instance.profile.company.name if hasattr(instance, 'profile') else "No Company"
    get_company.short_description = 'Assigned Agency'

    def get_inlines(self, request, obj=None):
        if not obj:
            return []
        return [ProfileInline]

# Re-register User
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# --- 3. BOOKING ADMIN (The Ledger) ---
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('booking_id', 'customer_name', 'company_badge', 'total_members', 'amount_paid', 'status_badge', 'created_at')
    list_filter = ('company', 'payment_status', 'created_at')
    search_fields = ('booking_id', 'customer_name', 'contact_mobile', 'receipt_number')
    readonly_fields = ('booking_id', 'created_at')
    
    fieldsets = (
        ('Reference', {
            'fields': ('booking_id', 'company', 'receipt_number', 'booking_date')
        }),
        ('Payer Details', {
            'fields': ('customer_name', 'contact_mobile', 'contact_email', 'address', 'cid_number')
        }),
        ('Manifest', {
            'fields': ('total_members', 'passenger_manifest')
        }),
        ('Financials', {
            'fields': ('tour_price', 'amount_paid', 'payment_status', 'payment_mode', 'cheque_number', 'cheque_date')
        }),
    )

    def company_badge(self, obj):
        # Color-code the company name for quick scanning
        return mark_safe(f'<span style="font-weight:bold; color:#2563eb;">{obj.company.name}</span>')
    company_badge.short_description = "Agency"

    def status_badge(self, obj):
        color = 'green' if obj.payment_status == 'Paid' else 'red'
        return mark_safe(f'<span style="color: white; background: {color}; padding: 3px 10px; border-radius: 10px; font-weight: bold; font-size: 10px;">{obj.payment_status.upper()}</span>')
    status_badge.short_description = "Payment Status"