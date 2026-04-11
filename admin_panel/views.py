from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Visitor
from core.models import User, SocietyMaintenanceSettings, Expense
from resident.models import Bill
from django.utils import timezone
from datetime import date
from django.contrib import messages
from django.db.models import Sum

@login_required
def dashboard(request):
    if request.user.role not in ['admin', 'company', 'secretary']:
        return redirect('resident_dashboard')
    
    # Society-specific stats for Secretary
    # Society-specific stats for Secretary
    society_name = request.user.society_name
    from core.models import Notice
    from resident.models import Complaint
    
    visitors = Visitor.objects.filter(unit__icontains=request.user.society_name[0] if request.user.society_name else "").order_by('-time_in')
    # Or just all if they are not filtered yet.
    visitors = Visitor.objects.all().order_by('-time_in')
    
    expenses = Expense.objects.filter(society_name=society_name).order_by('-created_at')
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    expenses_count = expenses.count()
    
    notices_count = Notice.objects.filter(society_name=society_name).count()
    complaints_count = Complaint.objects.filter(user__society_name=society_name, status='Open').count()
    
    from core.models import InviteCode
    invite_code = InviteCode.objects.filter(society_name=society_name).first()
    
    context = {
        'invite_code': invite_code.code if invite_code else '',
        'visitors': visitors,
        'expenses': expenses,
        'total_expenses': total_expenses,
        'expenses_count': expenses_count,
        'notices_count': notices_count,
        'complaints_count': complaints_count,
    }
    return render(request, 'admin_panel/dashboard.html', context)

@login_required
def visitors_list(request):
    if request.user.role not in ['admin', 'company', 'secretary']: return redirect('resident_dashboard')
    visitors = Visitor.objects.all()
    return render(request, 'admin_panel/visitors.html', {'visitors': visitors})

@login_required
def expenses_list(request):
    if request.user.role not in ['admin', 'company', 'secretary']: return redirect('resident_dashboard')
    
    society_name = request.user.society_name
    
    if request.method == 'POST':
        payee_name = request.POST.get('payee_name')
        amount = request.POST.get('amount')
        description = request.POST.get('description')
        receipt = request.FILES.get('receipt')
        
        Expense.objects.create(
            payee_name=payee_name,
            amount=amount,
            description=description,
            society_name=society_name,
            receipt=receipt
        )
        messages.success(request, f"Recorded expense for {payee_name}")
        return redirect('admin_expenses')
        
    expenses = Expense.objects.filter(society_name=society_name).order_by('-created_at')
    return render(request, 'admin_panel/expenses.html', {'expenses': expenses})

@login_required
def expense_delete(request, expense_id):
    if request.user.role != 'secretary': return redirect('home')
    expense = get_object_or_404(Expense, id=expense_id, society_name=request.user.society_name)
    expense.delete()
    messages.success(request, "Expense record deleted.")
    return redirect('admin_expenses')

@login_required
def management(request):
    if request.user.role not in ['admin', 'company', 'secretary']: return redirect('resident_dashboard')
    from core.models import InviteCode
    invite_code = InviteCode.objects.filter(society_name=request.user.society_name).first()
    return render(request, 'admin_panel/management.html', {
        'invite_code': invite_code.code if invite_code else ''
    })

@login_required
def maintenance_settings(request):
    if request.user.role != 'secretary': return redirect('home')
    
    settings, created = SocietyMaintenanceSettings.objects.get_or_create(
        society_name=request.user.society_name
    )
    
    if request.method == 'POST':
        settings.maintenance_charge = request.POST.get('maintenance_charge', 0)
        settings.due_day = request.POST.get('due_day', 15)
        settings.expected_payee_account = request.POST.get('expected_payee_account')
        
        if request.FILES.get('maintenance_qr'):
            settings.maintenance_qr = request.FILES.get('maintenance_qr')
            
        settings.save()
        messages.success(request, "Maintenance settings updated successfully!")
        return redirect('maintenance_settings')
        
    return render(request, 'admin_panel/maintenance_settings.html', {'settings': settings})

@login_required
def generate_bills(request):
    if request.user.role != 'secretary': return redirect('home')
    
    settings = get_object_or_404(SocietyMaintenanceSettings, society_name=request.user.society_name)
    # Only generate maintenance bills for OWNER residents; rental residents pay rent to their owner
    residents = User.objects.filter(society_name=request.user.society_name, role='resident', resident_role='owner')
    
    today = date.today()
    month_name = today.strftime("%B")
    year = today.year
    
    bills_created = 0
    for resident in residents:
        # Check if bill already exists for this month
        if not Bill.objects.filter(user=resident, month=month_name, year=year).exists():
            due_date = today.replace(day=int(settings.due_day))
            
            Bill.objects.create(
                user=resident,
                title=f"Maintenance - {month_name} {year}",
                maintenance_charge=settings.maintenance_charge,
                total_amount=settings.maintenance_charge,
                month=month_name,
                year=year,
                due_date=due_date
            )
            bills_created += 1
            
    messages.success(request, f"Generated {bills_created} bills for {month_name} {year}")
    return redirect('admin_dashboard')

# ─── Notices Management ───────────────────────────────────────────────────────

@login_required
def notices_list(request):
    if request.user.role != 'secretary': return redirect('home')
    from core.models import Notice
    notices = Notice.objects.filter(society_name=request.user.society_name).order_by('-created_at')
    return render(request, 'admin_panel/notices.html', {'notices': notices})

@login_required
def notice_create(request):
    if request.user.role != 'secretary': return redirect('home')
    from core.models import Notice
    
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        image = request.FILES.get('image')
        video = request.FILES.get('video')
        
        Notice.objects.create(
            title=title,
            content=content,
            image=image,
            video=video,
            society_name=request.user.society_name
        )
        messages.success(request, "Notice published successfully!")
        return redirect('notices_list')
        
    return render(request, 'admin_panel/notice_form.html')

@login_required
def notice_delete(request, notice_id):
    if request.user.role != 'secretary': return redirect('home')
    from core.models import Notice
    notice = get_object_or_404(Notice, id=notice_id, society_name=request.user.society_name)
    notice.delete()
    messages.success(request, "Notice deleted.")
    return redirect('notices_list')

@login_required
def cashbook_view(request):
    if request.user.role != 'secretary': return redirect('home')
    from core.models import PaymentProof, Expense
    society_name = request.user.society_name
    
    resident_records = PaymentProof.objects.filter(society_name=society_name, status__in=['verified', 'approved']).order_by('-created_at')
    other_records = Expense.objects.filter(society_name=society_name).order_by('-created_at')
    
    return render(request, 'admin_panel/cashbook.html', {
        'resident_records': resident_records,
        'other_records': other_records
    })

# ─── Complaints Management ────────────────────────────────────────────────────

@login_required
def complaints_list(request):
    if request.user.role != 'secretary': return redirect('home')
    from resident.models import Complaint
    complaints = Complaint.objects.filter(user__society_name=request.user.society_name).order_by('-created_at')
    return render(request, 'admin_panel/complaints.html', {'complaints': complaints})

@login_required
def complaint_resolve(request, complaint_id):
    if request.user.role != 'secretary': return redirect('home')
    from resident.models import Complaint
    complaint = get_object_or_404(Complaint, id=complaint_id, user__society_name=request.user.society_name)
    complaint.status = 'Resolved'
    complaint.save()
    messages.success(request, "Complaint marked as resolved.")
    return redirect('complaints_list_admin')
