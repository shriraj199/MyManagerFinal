from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from core.models import InviteCode, User, SocietyMaintenanceSettings

@login_required
def dashboard(request):
    if request.user.role != 'company':
        return redirect('resident_dashboard')
    
    # Get all invite codes created by this company
    invite_codes = InviteCode.objects.filter(company=request.user).order_by('-created_at')
    
    # Get all secretaries for societies managed by this company
    society_names = invite_codes.values_list('society_name', flat=True)
    secretaries = User.objects.filter(role='secretary', society_name__in=society_names)
    
    return render(request, 'company_panel/dashboard.html', {
        'invite_codes': invite_codes,
        'secretaries': secretaries
    })

@login_required
def generate_code(request):
    if request.user.role != 'company':
        return redirect('resident_dashboard')
        
    if request.method == 'POST':
        society_name = request.POST.get('society_name')
        maintenance_qr = request.FILES.get('maintenance_qr')
        
        if society_name:
            # Create a new invite code
            InviteCode.objects.create(
                company=request.user,
                society_name=society_name,
                maintenance_qr=maintenance_qr
            )
            
            # Also create/update the Maintenance Settings for this society
            settings, created = SocietyMaintenanceSettings.objects.get_or_create(
                society_name=society_name
            )
            if maintenance_qr:
                settings.maintenance_qr = maintenance_qr
                settings.save()
                
            messages.success(request, f'Invite code and settings generated for {society_name}!')
        else:
            messages.error(request, 'Society name is required.')
            
    return redirect('company_dashboard')

@login_required
def delete_society(request, society_name):
    if request.user.role != 'company':
        return redirect('resident_dashboard')
    
    import urllib.parse
    society_name = urllib.parse.unquote(society_name)
    
    # 1. CASCADE DELETE: All users associated with this society (Secretaries, Residents, Watchmen)
    deleted_count, _ = User.objects.filter(society_name=society_name).delete()
    
    # 2. Delete Invite Codes
    InviteCode.objects.filter(society_name=society_name).delete()
    
    # 3. Delete Maintenance Settings
    SocietyMaintenanceSettings.objects.filter(society_name=society_name).delete()
    
    # 4. Delete Subscription data if any
    try:
        from core.models import Subscription
        Subscription.objects.filter(society_name=society_name).delete()
    except Exception:
        # Table might not exist yet
        pass
    
    messages.success(request, f"Successfully deleted society '{society_name}' and {deleted_count} associated accounts.")
    return redirect('company_dashboard')

@login_required
def delete_secretary(request, secretary_id):
    if request.user.role != 'company':
        return redirect('resident_dashboard')
    
    from core.models import User
    sec = get_object_or_404(User, id=secretary_id, role='secretary')
    society_name = sec.society_name
    sec.delete()
    
    messages.success(request, f"Successfully deleted Secretary {sec.username} for society {society_name}.")
    return redirect('company_dashboard')

@login_required
def societies_list(request):
    if request.user.role != 'company':
        return redirect('resident_dashboard')
    
    society_names = InviteCode.objects.filter(company=request.user).values_list('society_name', flat=True).distinct()
    
    societies = []
    for name in society_names:
        resident_count = User.objects.filter(society_name=name, role='resident').count()
        societies.append({
            'name': name,
            'resident_count': resident_count
        })
        
    return render(request, 'company_panel/societies.html', {'societies': societies})

@login_required
def society_detail(request, society_name):
    if request.user.role != 'company':
        return redirect('resident_dashboard')
    
    import urllib.parse
    society_name = urllib.parse.unquote(society_name)
    
    # Get all owners in this society
    owners = User.objects.filter(society_name=society_name, role='resident', resident_role='owner').order_by('unit_number')
    
    # Check each owner for rentals
    members = []
    for owner in owners:
        is_rented = owner.rentals.exists()
        members.append({
            'owner': owner,
            'is_rented': is_rented
        })
    
    flat_count = owners.count()
    
    return render(request, 'company_panel/society_detail.html', {
        'society_name': society_name,
        'members': members,
        'flat_count': flat_count
    })

@login_required
def run_migrations(request):
    """Triggers database migrations from the browser."""
    if request.user.role != 'company':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Unauthorized")
    
    from django.core.management import call_command
    from django.http import HttpResponse
    import io

    output = io.StringIO()
    try:
        call_command('migrate', interactive=False, stdout=output)
        result = output.getvalue()
        return HttpResponse(f"<h3>Migrations Successful</h3><pre>{result}</pre><p><a href='/company/dashboard/'>Back to Dashboard</a></p>")
    except Exception as e:
        return HttpResponse(f"<h3>Migration Failed</h3><pre>{str(e)}</pre>")

@login_required
def pending_subscriptions(request):
    """Lists all subscriptions waiting for approval."""
    if request.user.role != 'company':
        return redirect('home')
    
    from core.models import Subscription
    pending = Subscription.objects.filter(status__in=['pending', 'review']).order_by('-start_date')
    
    return render(request, 'company_panel/subscriptions.html', {
        'pending_subscriptions': pending
    })

@login_required
def approve_subscription(request, subscription_id):
    """Activates a society's subscription."""
    if request.user.role != 'company':
        return redirect('home')
    
    from core.models import Subscription
    sub = get_object_or_404(Subscription, id=subscription_id)
    
    # Deactivate any other active sub for this society first
    Subscription.objects.filter(society_name=sub.society_name, is_active=True).update(is_active=False, status='expired')
    
    sub.status = 'active'
    sub.is_active = True
    sub.save()
    
    messages.success(request, f"Subscription for {sub.society_name} has been activated!")
    return redirect('pending_subscriptions')

@login_required
def dangerous_flush_database(request):
    """CRITICAL: Deletes ALL data from the database."""
    if request.user.role != 'company':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Only the company can flush the database.")
    
    from django.core.management import call_command
    from django.contrib.auth import logout
    from django.http import HttpResponse
    
    # Perform the flush
    call_command('flush', interactive=False)
    
    # Logout the user as their session/user is now gone
    logout(request)
    
    return HttpResponse("<h3>Database Flushed Successfully.</h3><p>All data has been deleted. You have been logged out. Please <a href='/register/'>Register</a> a new Company account.</p>")
