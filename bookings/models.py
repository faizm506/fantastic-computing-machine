from django.db import models

# Create your models here.
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Company(models.Model):
    name = models.CharField(max_length=255)
    id_prefix = models.CharField(max_length=10, default="VT") 
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)
    
    def __str__(self): return self.name

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    company = models.ForeignKey(Company, on_delete=models.CASCADE)

    def __str__(self): return f"{self.user.username} ({self.company.name})"

import uuid
from django.db import models

class Booking(models.Model):
    # --- EXISTING FIELDS ---
    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='bookings')
    booking_id = models.CharField(max_length=50, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # --- DOCUMENT HEADER INFO ---
    # Captures "Receipt No. 53" [cite: 9]
    receipt_number = models.CharField(max_length=50, blank=True, null=True)
    # Captures the manual "Date" written on the receipt [cite: 8]
    booking_date = models.DateField(null=True, blank=True)
    # Captures "C.I.D No." from top left [cite: 5]
    cid_number = models.CharField(max_length=50, blank=True, null=True)

    # --- CUSTOMER / PAYER DETAILS ---
    # "Received with thanks from" [cite: 10]
    customer_name = models.CharField(max_length=200)
    # "Address" [cite: 14]
    address = models.TextField(blank=True, null=True)
    # "Mobile" [cite: 16]
    contact_mobile = models.CharField(max_length=20, blank=True, null=True)
    # "Email" [cite: 11]
    contact_email = models.EmailField(blank=True, null=True)
    # "T.No. (O)" and "(R)" [cite: 12, 15]
    phone_office = models.CharField(max_length=20, blank=True, null=True)
    phone_residence = models.CharField(max_length=20, blank=True, null=True)

    # --- PASSENGER MANIFEST (Table) ---
    total_members = models.PositiveIntegerField(default=1)
    # Stores the table columns: Name, PAN, Passport, DOB, Issue/Exp Date, Place of Issue 
    # Example format: [{"name": "Ali", "passport": "A123", "pan": "ABC..."}]
    passenger_manifest = models.JSONField(default=list, blank=True)

    # --- PAYMENT & BILLING ---
    # "the sum of Rupees" (Amount paid now) [cite: 13]
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Total package cost
    tour_price = models.DecimalField(max_digits=12, decimal_places=2)
    
    # "by Cash / Cheque No." 
    PAYMENT_MODES = [('Cash', 'Cash'), ('Cheque', 'Cheque'), ('Online', 'Online')]
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default='Cash')
    
    # Cheque details if applicable [cite: 17, 23]
    cheque_number = models.CharField(max_length=50, blank=True, null=True)
    cheque_date = models.DateField(blank=True, null=True)

    # "In advance / part / full / final payment" [cite: 18]
    PAYMENT_STAGES = [
        ('Advance', 'Advance'),
        ('Part', 'Part Payment'),
        ('Full', 'Full Payment'),
        ('Final', 'Final Payment')
    ]
    payment_stage = models.CharField(max_length=20, choices=PAYMENT_STAGES, default='Advance')

    # "Final Payment before Dt." 
    final_payment_due_date = models.DateField(blank=True, null=True)

    # "Payment Status" (Computed or Manual)
    payment_status = models.CharField(max_length=20, choices=[('Pending', 'Pending'), ('Paid', 'Paid')], default='Pending')

    # --- EXTRAS ---
    # "Remark" field [cite: 21]
    remarks = models.TextField(blank=True, null=True)
    # "Allotment" [cite: 19]
    allotment_details = models.CharField(max_length=255, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.booking_id:
            self.booking_id = f"{self.company.id_prefix}-{uuid.uuid4().hex[:7].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.booking_id} - {self.customer_name}"
    
class ActivityLog(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255) # e.g., "Created New Booking"
    reference_id = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']