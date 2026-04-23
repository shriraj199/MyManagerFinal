from django.db import models
from django.conf import settings

class Bill(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bills')
    title = models.CharField(max_length=100)
    
    # Breakdown of charges
    maintenance_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Late fee tracking
    late_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_late_applied = models.BooleanField(default=False)
    
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=[('Pending', 'Pending'), ('Paid', 'Paid')], default='Pending')
    
    def get_signature(self):
        from django.conf import settings
        import hashlib
        secret = settings.SECRET_KEY
        return hashlib.sha256(f"{self.id}{secret}".encode()).hexdigest()

    # Billing period
    month = models.CharField(max_length=20, blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    months_covered = models.PositiveIntegerField(default=1, help_text="Number of months this bill covers")
    
    date = models.DateField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({self.month} {self.year}) - {self.user.username}"

class Complaint(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='complaints')
    title = models.CharField(max_length=200)
    complaint_type = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=[('Open', 'Open'), ('Resolved', 'Resolved')], default='Open')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.status}"
