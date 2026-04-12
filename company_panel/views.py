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
    
    # 1. CASCADE DELETE: All users associated with this society (Secretaries, Residents, Watchmen)
    deleted_count, _ = User.objects.filter(society_name=society_name).delete()
    
    # 2. Delete Invite Codes
    InviteCode.objects.filter(society_name=society_name).delete()
    
    # 3. Delete Maintenance Settings
    SocietyMaintenanceSettings.objects.filter(society_name=society_name).delete()
    
    # 4. Delete Subscription data if any
    from core.models import Subscription
    Subscription.objects.filter(society_name=society_name).delete()
    
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
