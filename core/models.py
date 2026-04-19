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
    is_pro_member = models.BooleanField(default=True)

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
        
        due_day = getattr(settings, 'due_day', 15)
        late_fee_charge = getattr(settings, 'late_fee_charge', Decimal('0.00'))
        
        if current_bill:
            # If bill exists, use its total but subtract credit
            current_due = current_bill.total_amount - excess_payment
            
            # Apply late fee ONLY if not already applied in the Bill object and it's past due day
            if now.day > due_day and current_due > 0.01 and not current_bill.is_late_applied:
                current_due += late_fee_charge
        else:
            # Ungenerated: Monthly Charge - Credit
            current_due = base_charge - excess_payment
            
            # Apply Late Fee if day > due_day and still unpaid (> 0.01)
            if now.day > due_day and current_due > 0.01:
                current_due += late_fee_charge
                
        return current_due

    def get_rent_balance(self):
        """Dynamic rent balance calculation for rental users."""
        from .models import RentalChargeSettings
        from django.utils import timezone
        from decimal import Decimal
        from django.db import models
        
        if self.resident_role != 'rental':
            return Decimal('0.00')
            
        settings = RentalChargeSettings.objects.filter(rental_user=self).first()
        if not settings:
            return Decimal('0.00')
            
        # Simplified for now: just current month's rent minus all payments made THIS month
        now = timezone.now()
        this_month_paid = self.rent_proofs.filter(
            status__in=['verified', 'approved', 'flagged'],
            created_at__month=now.month,
            created_at__year=now.year
        ).aggregate(models.Sum('extracted_amount'))['extracted_amount__sum'] or Decimal('0.00')
        
        balance = settings.monthly_rent - this_month_paid
        return max(Decimal('0.00'), balance)

    def is_subscription_active(self):
        if self.role in ['company', 'secretary']:
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

    @property
    def is_on_trial(self):
        """Returns True if the society has no subscription history and is within trial period."""
        from .models import Subscription
        if self.role != 'secretary':
            return False
            
        has_subscription = Subscription.objects.filter(
            society_name=self.society_name,
            status__in=['active', 'pending', 'review']
        ).exists()
        
        return not has_subscription and self.trial_days_left > 0

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
    late_fee_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Fixed amount to charge if paid after due date")

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

from django.utils import timezone

class LedgerAccount(models.Model):
    ACCOUNT_TYPES = [
        ('Asset', 'Asset'),
        ('Liability', 'Liability'),
        ('Equity', 'Equity'),
        ('Revenue', 'Revenue'),
        ('Expense', 'Expense'),
    ]
    STATEMENT_TYPES = [
        ('Trading', 'Trading Account'),
        ('PL', 'Profit & Loss Account'),
        ('BalanceSheet', 'Balance Sheet'),
    ]
    society_name = models.CharField(max_length=200, db_index=True)
    name = models.CharField(max_length=200) # e.g. 'Cash', 'Bank', 'Sales'
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    statement_type = models.CharField(max_length=20, choices=STATEMENT_TYPES)
    
    def __str__(self):
        return f"{self.name} ({self.society_name})"
        
class JournalEntry(models.Model):
    society_name = models.CharField(max_length=200, db_index=True)
    date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Entry {self.id} - {self.description}"
        
class JournalItem(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='items')
    account = models.ForeignKey(LedgerAccount, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    entry_type = models.CharField(max_length=2, choices=[('Dr', 'Debit'), ('Cr', 'Credit')])
    
    def __str__(self):
        return f"{self.account.name} - {self.entry_type} {self.amount}"

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

def get_default_accounts(society_name):
    bank, _ = LedgerAccount.objects.get_or_create(society_name=society_name, name='Bank Account', defaults={'account_type': 'Asset', 'statement_type': 'BalanceSheet'})
    maintenance, _ = LedgerAccount.objects.get_or_create(society_name=society_name, name='Maintenance Income', defaults={'account_type': 'Revenue', 'statement_type': 'PL'})
    expense_acc, _ = LedgerAccount.objects.get_or_create(society_name=society_name, name='General Expenses', defaults={'account_type': 'Expense', 'statement_type': 'PL'})
    return bank, maintenance, expense_acc

@receiver(post_save, sender=Expense)
def auto_journal_expense(sender, instance, created, **kwargs):
    if created:
        bank, _, expense_acc = get_default_accounts(instance.society_name)
        ref_desc = f"New Expense: {instance.payee_name} [REF:EXP-{instance.id}]"
        
        entry = JournalEntry.objects.create(
            society_name=instance.society_name,
            description=ref_desc
        )
        JournalItem.objects.create(entry=entry, account=expense_acc, amount=instance.amount, entry_type='Dr')
        JournalItem.objects.create(entry=entry, account=bank, amount=instance.amount, entry_type='Cr')

@receiver(post_delete, sender=Expense)
def delete_auto_journal_expense(sender, instance, **kwargs):
    ref_desc = f"[REF:EXP-{instance.id}]"
    JournalEntry.objects.filter(society_name=instance.society_name, description__endswith=ref_desc).delete()

@receiver(post_save, sender=PaymentProof)
def auto_journal_payment(sender, instance, created, **kwargs):
    ref_desc = f"Maintenance Receipt [REF:PAY-{instance.id}]"
    
    if instance.status in ['verified', 'approved']:
        if not JournalEntry.objects.filter(description__endswith=ref_desc).exists():
            bank, maintenance, _ = get_default_accounts(instance.society_name)
            amount = instance.extracted_amount if instance.extracted_amount else 0
            if amount > 0:
                entry = JournalEntry.objects.create(
                    society_name=instance.society_name,
                    description=ref_desc
                )
                JournalItem.objects.create(entry=entry, account=bank, amount=amount, entry_type='Dr')
                JournalItem.objects.create(entry=entry, account=maintenance, amount=amount, entry_type='Cr')
    else:
        # If status changed back to pending/rejected, remove entry
        JournalEntry.objects.filter(society_name=instance.society_name, description__endswith=ref_desc).delete()

@receiver(post_delete, sender=PaymentProof)
def delete_auto_journal_payment(sender, instance, **kwargs):
    ref_desc = f"[REF:PAY-{instance.id}]"
    JournalEntry.objects.filter(society_name=instance.society_name, description__endswith=ref_desc).delete()


