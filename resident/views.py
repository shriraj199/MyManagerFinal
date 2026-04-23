from django.conf import settings
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.template.loader import get_template
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
from .models import Bill, Complaint
from django.utils import timezone
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import get_user_model

User = get_user_model()


@login_required
def dashboard(request):
    if request.user.role != 'resident':
        return redirect('admin_dashboard')

    bills = request.user.bills.filter(status='Pending')
    complaints = request.user.complaints.all()

    # Total pending now includes multi-month debt and automatically applied late fees
    total_pending = request.user.get_maintenance_balance()

    context = {
        'bills_count': bills.count(),
        'total_pending': total_pending,
        'current_balance': request.user.get_maintenance_balance(),
        'complaints': complaints,
        'is_owner': request.user.resident_role == 'owner',
        'is_rental': request.user.resident_role == 'rental',
    }

    # For rental residents: show their rent info from their owner
    if request.user.resident_role == 'rental':
        try:
            from core.models import RentalChargeSettings
            rental_charge = RentalChargeSettings.objects.get(rental_user=request.user)
            context['rental_charge'] = rental_charge
        except:
            context['rental_charge'] = None

    # For owner residents: show count of their rentals
    if request.user.resident_role == 'owner':
        from core.models import RentalChargeSettings
        context['rental_count'] = RentalChargeSettings.objects.filter(owner=request.user).count()

    # --- SOCIETY NOTICES ---
    from core.models import Notice
    context['notices'] = Notice.objects.filter(society_name=request.user.society_name).order_by('-created_at')[:5]

    # --- ONE-TIME WELCOME POPUP ---
    context['show_welcome'] = not request.user.has_seen_welcome
    if not request.user.has_seen_welcome:
        request.user.has_seen_welcome = True
        request.user.save(update_fields=['has_seen_welcome'])

    return render(request, 'resident/dashboard.html', context)


@login_required
def bills_list(request):
    if request.user.role != 'resident':
        return redirect('admin_dashboard')

    bills = request.user.bills.all().order_by('-year', '-month')
    today = date.today()

    # Late fees are now automatically applied by request.user.get_maintenance_balance() 
    # whenever it is called, or we can explicitly call it here to ensure bills are updated.
    request.user.get_maintenance_balance()

    return render(request, 'resident/bills.html', {
        'bills': bills,
        'today': today,
        'is_owner': request.user.resident_role == 'owner',
        'is_rental': request.user.resident_role == 'rental',
    })


@login_required
def complaints_list(request):
    if request.user.role != 'resident':
        return redirect('admin_dashboard')
    complaints = request.user.complaints.all()
    return render(request, 'resident/complaints.html', {'complaints': complaints})


@login_required
def more_options(request):
    if request.user.role != 'resident':
        return redirect('admin_dashboard')
    return render(request, 'resident/more.html', {
        'is_owner': request.user.resident_role == 'owner',
        'is_rental': request.user.resident_role == 'rental',
    })


@login_required
def receipt_view(request, bill_id):
    if request.user.role != 'resident':
        return redirect('admin_dashboard')
    bill = get_object_or_404(Bill, id=bill_id, user=request.user, status='Paid')
    return render(request, 'resident/receipt.html', {'bill': bill})


import hashlib
def get_receipt_signature(bill_id):
    """Generates a secure signature for a bill receipt to allow public but protected access."""
    # Using a simple hash with the secret key
    secret = settings.SECRET_KEY
    return hashlib.sha256(f"{bill_id}{secret}".encode()).hexdigest()

@login_required
def generate_receipt_pdf(request, bill_id):
    if request.user.role != 'resident':
        return redirect('admin_dashboard')
    bill = get_object_or_404(Bill, id=bill_id, user=request.user, status='Paid')
    return _generate_pdf_response(bill)

def public_generate_receipt_pdf(request):
    """Allows downloading a receipt without login IF the signature is valid. 
    Fixes Android WebView session issues."""
    bill_id = request.GET.get('bill_id')
    signature = request.GET.get('signature')
    
    if not bill_id or signature != get_receipt_signature(bill_id):
        return HttpResponse("Invalid Signature", status=403)
        
    bill = get_object_or_404(Bill, id=bill_id, status='Paid')
    return _generate_pdf_response(bill)

def _generate_pdf_response(bill):
    """Shared logic to generate the PDF response."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('title', parent=styles['Title'],
                                  fontSize=20, textColor=colors.HexColor('#1a1a2e'),
                                  spaceAfter=6)
    sub_style = ParagraphStyle('sub', parent=styles['Normal'],
                                fontSize=10, textColor=colors.grey, spaceAfter=12)
    
    story.append(Paragraph('PAYMENT RECEIPT', title_style))
    story.append(Paragraph(f'Receipt #{bill.id}', sub_style))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e0e0e0')))
    story.append(Spacer(1, 0.4*cm))

    user = bill.user
    data = [
        ['Resident Name', user.get_full_name() or user.username],
        ['Society', user.society_name or '—'],
        ['Unit No.', user.unit_number or '—'],
        ['Bill Period', f"{bill.month or ''} {bill.year or ''}"],
        ['Bill Status', bill.status],
        ['Transaction ID', bill.transaction_id or '—'],
        ['Payment Date', str(bill.payment_date or '—')],
        ['Maintenance Charge', f'Rs. {bill.maintenance_charge}'],
        ['Late Fee', f'Rs. {bill.late_fee_amount}'],
        ['Total Amount Paid', f'Rs. {bill.total_amount}'],
    ]

    table = Table(data, colWidths=[6*cm, 10*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#555555')),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#e0e0e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.8*cm))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e0e0e0')))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph('This is a system-generated receipt.', ParagraphStyle(
        'footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{bill.id}.pdf"'
    response.write(pdf)
    return response


# ─── Owner: Rental Management ─────────────────────────────────────────────────

@login_required
def rental_management(request):
    """Owner can see all their rental settings and manage them."""
    if request.user.role != 'resident' or request.user.resident_role != 'owner':
        return redirect('resident_dashboard')

    from core.models import RentalChargeSettings, RentPaymentProof
    rentals = RentalChargeSettings.objects.filter(owner=request.user).select_related('rental_user')
    
    # All tenant accounts created/owned by this owner
    all_tenants = User.objects.filter(
        role='resident', resident_role='rental',
        owner=request.user
    )

    # Rent proofs received by this owner
    rent_proofs = RentPaymentProof.objects.filter(owner=request.user).order_by('-created_at')

    return render(request, 'resident/rental_management.html', {
        'rentals': rentals,
        'all_tenants': all_tenants,
        'rent_proofs': rent_proofs,
    })


@login_required
def rental_add_profile(request):
    """Owner creates a new rental (tenant) user account directly from their portal."""
    if request.user.role != 'resident' or request.user.resident_role != 'owner':
        return redirect('resident_dashboard')

    if request.method == 'POST':
        from django.contrib.auth import get_user_model
        from django.db import IntegrityError
        User_ = get_user_model()

        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip()
        mobile = request.POST.get('mobile', '').strip()
        unit_number = request.user.unit_number # Locked to owner's unit
        password = request.POST.get('password', '').strip()

        if not email or not password or not full_name:
            messages.error(request, 'Full name, email and password are required.')
            return render(request, 'resident/rental_add_profile.html')

        if User_.objects.filter(username=email).exists():
            messages.error(request, f'An account with email "{email}" already exists.')
            return render(request, 'resident/rental_add_profile.html')

        try:
            rental_user = User_.objects.create_user(
                username=email,
                email=email,
                first_name=full_name,
                password=password,
                role='resident',
                resident_role='rental',
                mobile_number=mobile,
                society_name=request.user.society_name,
                unit_number=unit_number,
                owner=request.user,
            )
            messages.success(request, f'✅ Rental profile for {full_name} created! They can now log in with {email}.')
            return redirect('rental_management')
        except IntegrityError:
            messages.error(request, 'Could not create account. Please try again.')
            return render(request, 'resident/rental_add_profile.html')

    return render(request, 'resident/rental_add_profile.html')


@login_required
def rental_tenant_delete(request, tenant_id):
    """Owner can delete a rental tenant's account they created."""
    if request.user.role != 'resident' or request.user.resident_role != 'owner':
        return redirect('resident_dashboard')

    tenant = get_object_or_404(User, id=tenant_id, role='resident', resident_role='rental', owner=request.user)
    name = tenant.first_name or tenant.username
    tenant.delete()
    messages.success(request, f'Rental profile for {name} has been removed.')
    return redirect('rental_management')


@login_required
def rental_charge_create(request):
    """Owner creates a new rental charge setting."""
    if request.user.role != 'resident' or request.user.resident_role != 'owner':
        return redirect('resident_dashboard')

    from core.models import RentalChargeSettings

    # Already-linked rental users
    linked_ids = RentalChargeSettings.objects.filter(owner=request.user).values_list('rental_user_id', flat=True)
    available_rentals = User.objects.filter(
        role='resident', resident_role='rental',
        society_name=request.user.society_name,
        owner=request.user
    ).exclude(id__in=linked_ids)

    if request.method == 'POST':
        rental_user_id = request.POST.get('rental_user_id')
        monthly_rent = request.POST.get('monthly_rent', 0)
        due_day = request.POST.get('due_day', 5)
        account_number = request.POST.get('account_number', '')
        notes = request.POST.get('notes', '')

        rental_user = None
        if rental_user_id:
            rental_user = User.objects.filter(id=rental_user_id, role='resident', resident_role='rental', owner=request.user).first()

        rc = RentalChargeSettings.objects.create(
            owner=request.user,
            rental_user=rental_user,
            monthly_rent=monthly_rent,
            due_day=due_day,
            account_number=account_number,
            notes=notes,
        )

        if request.FILES.get('rent_qr'):
            rc.rent_qr = request.FILES.get('rent_qr')
            rc.save()

        messages.success(request, "✅ Rental charge settings created successfully!")
        return redirect('rental_management')

    return render(request, 'resident/rental_charge_form.html', {
        'available_rentals': available_rentals,
        'form_title': 'Create Rental Charge',
        'submit_label': 'Create',
    })


@login_required
def rental_charge_edit(request, rc_id):
    """Owner edits an existing rental charge."""
    if request.user.role != 'resident' or request.user.resident_role != 'owner':
        return redirect('resident_dashboard')

    from core.models import RentalChargeSettings
    rc = get_object_or_404(RentalChargeSettings, id=rc_id, owner=request.user)

    # Rentals available to link (excluding already-linked ones from OTHER settings)
    linked_ids = RentalChargeSettings.objects.filter(owner=request.user).exclude(id=rc.id).values_list('rental_user_id', flat=True)
    available_rentals = User.objects.filter(
        role='resident', resident_role='rental',
        society_name=request.user.society_name,
        owner=request.user
    ).exclude(id__in=linked_ids)

    if request.method == 'POST':
        rental_user_id = request.POST.get('rental_user_id')
        rc.monthly_rent = request.POST.get('monthly_rent', rc.monthly_rent)
        rc.due_day = request.POST.get('due_day', rc.due_day)
        rc.account_number = request.POST.get('account_number', rc.account_number)
        rc.notes = request.POST.get('notes', rc.notes)

        if rental_user_id:
            rental_user = User.objects.filter(id=rental_user_id, role='resident', resident_role='rental', owner=request.user).first()
            rc.rental_user = rental_user

        if request.FILES.get('rent_qr'):
            rc.rent_qr = request.FILES.get('rent_qr')

        rc.save()
        messages.success(request, "✅ Rental charge updated successfully!")
        return redirect('rental_management')

    return render(request, 'resident/rental_charge_form.html', {
        'rc': rc,
        'available_rentals': available_rentals,
        'form_title': 'Edit Rental Charge',
        'submit_label': 'Save Changes',
    })


@login_required
def rental_charge_delete(request, rc_id):
    """Owner deletes a rental charge setting."""
    if request.user.role != 'resident' or request.user.resident_role != 'owner':
        return redirect('resident_dashboard')

    from core.models import RentalChargeSettings
    rc = get_object_or_404(RentalChargeSettings, id=rc_id, owner=request.user)
    rc.delete()
    messages.success(request, "Rental charge deleted.")
    return redirect('rental_management')


@login_required
def rental_dashboard(request):
    """Rental resident sees their rent details set by their owner."""
    if request.user.role != 'resident' or request.user.resident_role != 'rental':
        return redirect('resident_dashboard')

    from core.models import RentalChargeSettings
    try:
        rental_charge = RentalChargeSettings.objects.get(rental_user=request.user)
    except RentalChargeSettings.DoesNotExist:
        rental_charge = None

    return render(request, 'resident/rental_dashboard.html', {
        'rental_charge': rental_charge,
        'owner': request.user.owner,
    })
