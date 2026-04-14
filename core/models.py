from django.contrib.auth.models import AbstractUser
from django.db import models
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile
import os

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

def process_image(image_field):
    """Converts HEIC to JPEG and optimizes images."""
    if not image_field:
        return
    
    img_name = os.path.basename(image_field.name)
    name, ext = os.path.splitext(img_name)
    
    # If it's a HEIC/HEIF file, we convert it to JPEG
    if ext.lower() in ['.heic', '.heif']:
        img = Image.open(image_field)
        buffer = BytesIO()
        img.convert('RGB').save(buffer, format='JPEG', quality=85)
        new_image = ContentFile(buffer.getvalue())
        image_field.save(f"{name}.jpg", new_image, save=False)

class User(AbstractUser):
    ROLE_CHOICES = (
        ('secretary', 'Secretary'),
        ('company', 'Company'),
        ('resident', 'Residential'),
        ('watchman', 'Watchman'),
    )
    RESIDENT_ROLE_CHOICES = (
        ('owner', 'Owner'),
        ('rental', 'Rental'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='resident')
    resident_role = models.CharField(max_length=10, choices=RESIDENT_ROLE_CHOICES, default='owner', blank=True, null=True)
    mobile_number = models.CharField(max_length=15, blank=True, null=True)
    society_name = models.CharField(max_length=200, blank=True, null=True)
    upi_id = models.CharField(max_length=100, blank=True, null=True)
    upi_name = models.CharField(max_length=200, blank=True, null=True)
    unit_number = models.CharField(max_length=20, blank=True, null=True)
    # For rentals: link to their owner
    owner = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='rentals', limit_choices_to={'resident_role': 'owner'})
    has_seen_welcome = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username} ({self.role})"

    def get_maintenance_balance(self):
        """Calculates balance for the current month, carrying over credits but resetting debts."""
        from resident.models import Bill
        from decimal import Decimal
        from django.utils import timezone
        
        now = timezone.now()
        month_name = now.strftime("%B")
        year = now.year
        
        # 1. Historical Credit Carry-over
        # Total payments made by user
        total_payments = self.payment_proofs.filter(status__in=['verified', 'approved', 'flagged']).aggregate(models.Sum('extracted_amount'))['extracted_amount__sum'] or Decimal('0.00')
        
        # Total liabilities generated BEFORE this month
        historical_liabilities = Bill.objects.filter(user=self).exclude(month=month_name, year=year).aggregate(models.Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
        
        # Calculate excess payment (credit) - we reset debts so excess is never < 0
        excess_payment = max(Decimal('0.00'), total_payments - historical_liabilities)
        
        # 2. Current Month Dues
        from .models import SocietyMaintenanceSettings
        settings = SocietyMaintenanceSettings.objects.filter(society_name=self.society_name).first()
        if not settings:
            return -excess_payment
            
        base_charge = settings.maintenance_charge
        
        # Check if a bill for THIS month already exists
        current_bill = Bill.objects.filter(user=self, month=month_name, year=year).first()
        
        if current_bill:
            # If bill exists, use its total but subtract credit
            current_due = current_bill.total_amount - excess_payment
        else:
            # Ungenerated: Monthly Charge - Credit
            current_due = base_charge - excess_payment
            
            # 3. Apply Late Fee (21%) if day > 15 and still unpaid
            if now.day > 15 and current_due > 0:
                current_due += (base_charge * Decimal('0.21'))
                
        return current_due

    @property
    def is_subscription_active(self):
        if self.role == 'company':
            return True
        
        from django.utils import timezone
        # If no society name (newly registered), allow 7 day trial
        if not self.society_name:
            diff = timezone.now() - self.date_joined
            return diff.days < 7

        # Check for active subscription for this society
        from .models import Subscription
        active_sub = Subscription.objects.filter(
            society_name=self.society_name, 
            is_active=True, 
            end_date__gt=timezone.now()
        ).exists()
        
        if active_sub:
            return True
            
        # Fallback to trial based on registration date
        diff = timezone.now() - self.date_joined
        return diff.days < 7

    @property
    def trial_days_left(self):
        from django.utils import timezone
        diff = timezone.now() - self.date_joined
        remaining = 7 - diff.days
        return max(0, remaining)

import string
import random

def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

class InviteCode(models.Model):
    code = models.CharField(max_length=20, unique=True, default=generate_invite_code)
    society_name = models.CharField(max_length=200)
    company = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'company'}, related_name='invite_codes')
    maintenance_qr = models.ImageField(upload_to='maintenance_qrs/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.maintenance_qr:
            process_image(self.maintenance_qr)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.society_name} - {self.code}"

class PaymentProof(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('verified', 'Verified (Auto)'),
        ('flagged', 'Flagged (Date Mismatch)'),
        ('approved', 'Approved (Manual)'),
        ('rejected', 'Rejected'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_proofs')
    society_name = models.CharField(max_length=200)
    proof_image = models.ImageField(upload_to='payment_proofs/')
    extracted_date = models.DateField(blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    extracted_sender = models.CharField(max_length=200, blank=True, null=True)
    extracted_account_digits = models.CharField(max_length=10, blank=True, null=True)
    extracted_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.proof_image:
            process_image(self.proof_image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Proof by {self.user.username} for {self.society_name} ({self.status})"

class Subscription(models.Model):
    PLAN_CHOICES = [
        ('1-250', '1-250 Flats'),
        ('251-500', '251-500 Flats'),
        ('501+', '501 & Above Flats'),
    ]
    DURATION_CHOICES = [
        (1, '1 Month'),
        (6, '6 Months'),
        (12, '1 Year'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('review', 'Under Review'),
        ('active', 'Active'),
        ('expired', 'Expired'),
    ]
    
    society_name = models.CharField(max_length=200)
    # Temporary: Use ID instead of ForeignKey to avoid CASCADE crashes while table is missing
    secretary_id = models.PositiveIntegerField(null=True, blank=True)
    plan_tier = models.CharField(max_length=20, choices=PLAN_CHOICES)
    duration_months = models.IntegerField(choices=DURATION_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_proof = models.ImageField(upload_to='subscription_proofs/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.society_name} - {self.plan_tier} ({self.duration_months}m)"

class SocietyMaintenanceSettings(models.Model):
    society_name = models.CharField(max_length=200, unique=True)
    maintenance_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    maintenance_qr = models.ImageField(upload_to='maintenance_qrs/', blank=True, null=True)
    expected_payee_account = models.CharField(max_length=10, blank=True, null=True, help_text="Last 4 digits of your bank account (e.g. 5200)")
    due_day = models.PositiveSmallIntegerField(default=15, help_text="Day of the month when late fee starts (e.g. 15)")
    late_fee_percentage = models.PositiveSmallIntegerField(default=21, help_text="Percentage of late fee tax (e.g. 21)")

    def save(self, *args, **kwargs):
        if self.maintenance_qr:
            process_image(self.maintenance_qr)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Settings for {self.society_name}"


class RentalChargeSettings(models.Model):
    """Settings set by an Owner for their Rental tenant."""
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rental_charge_settings', limit_choices_to={'resident_role': 'owner'})
    rental_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='rental_charge', limit_choices_to={'resident_role': 'rental'}, null=True, blank=True)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    due_day = models.PositiveSmallIntegerField(default=5, help_text="Day of month when rent is due")
    account_number = models.CharField(max_length=50, blank=True, null=True, help_text="Owner's Bank Account Number")
    rent_qr = models.ImageField(upload_to='rent_qrs/', blank=True, null=True)
    notes = models.TextField(blank=True, null=True, help_text="Any notes for the rental (e.g. unit details)")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.rent_qr:
            process_image(self.rent_qr)
        super().save(*args, **kwargs)

    def __str__(self):
        rental_name = self.rental_user.username if self.rental_user else 'Unassigned'
        return f"Rent: {self.owner.username} → {rental_name} (₹{self.monthly_rent}/mo)"

class RentPaymentProof(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('verified', 'Verified (Auto)'),
        ('flagged', 'Flagged (Mismatch)'),
        ('approved', 'Approved (Manual)'),
        ('rejected', 'Rejected'),
    )
    rental_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rent_proofs')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_rent_proofs')
    proof_image = models.ImageField(upload_to='rent_proofs/')
    extracted_date = models.DateField(blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    extracted_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    extracted_account_digits = models.CharField(max_length=10, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.proof_image:
            process_image(self.proof_image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Rent Proof from {self.rental_user.username} to {self.owner.username}"


class Notice(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    image = models.ImageField(upload_to='notices/images/', blank=True, null=True)
    video = models.FileField(upload_to='notices/videos/', blank=True, null=True)
    society_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.image:
            process_image(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.society_name} - {self.title}"


class Expense(models.Model):
    payee_name = models.CharField(max_length=200)  # e.g., "Watchman", "Cleaner", "Plumber"
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    society_name = models.CharField(max_length=200, db_index=True)
    receipt = models.ImageField(upload_to='expenses/receipts/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.receipt:
            process_image(self.receipt)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.payee_name} - ₹{self.amount} ({self.society_name})"
