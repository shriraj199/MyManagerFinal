from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import HttpResponse, Http404, JsonResponse
from django.template.loader import get_template
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from io import BytesIO
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, get_user_model
from django.urls import reverse
from django.db import IntegrityError
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from decimal import Decimal
from datetime import date, datetime
import re, os
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum
from resident.models import Bill
from PIL import Image
import google.generativeai as genai
import json

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

def add_pdf_watermark(canvas, doc):
    """Draws a light watermark in the center of the PDF page."""
    from django.contrib.staticfiles import finders
    canvas.saveState()
    try:
        # Use finders to get the correct path in production/Vercel
        img_path = finders.find('core/pwa/TheManager.jpeg')
        if img_path:
            canvas.setFillAlpha(0.15)  # Slightly darker for better visibility
            w, h = doc.pagesize
            # Center the logo (7cm x 7cm)
            canvas.drawImage(img_path, w/2 - 3.5*cm, h/2 - 3.5*cm, width=7*cm, height=7*cm, mask='auto', preserveAspectRatio=True)
    except Exception as e:
        print(f"Watermark rendering error: {e}")
    canvas.restoreState()

User = get_user_model()

def force_migrate(request):
    from django.core.management import call_command
    from io import StringIO
    out = StringIO()
    call_command('migrate', interactive=False, stdout=out)
    return HttpResponse(f"<pre>{out.getvalue()}</pre>")

@never_cache
@csrf_protect
def register(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        full_name = request.POST.get('full_name', '')
        password = request.POST.get('password')
        role = request.POST.get('role', 'resident')
        mobile = request.POST.get('mobile')
        unit_number = request.POST.get('unit_number', '')

        if role in ['secretary', 'resident']:
            invite_code = request.POST.get('invite_code')
            if not invite_code:
                messages.error(request, 'Invite code is required.')
                return render(request, 'core/register.html')

            from .models import InviteCode
            invite_obj = InviteCode.objects.filter(code=invite_code).first()
            if not invite_obj:
                messages.error(request, 'Invalid invite code.')
                return render(request, 'core/register.html')

            society = invite_obj.society_name

            if role == 'secretary':
                existing_secretary = User.objects.filter(role='secretary', society_name=society).exists()
                if existing_secretary:
                    messages.error(request, 'A secretary already exists for this society.')
                    return render(request, 'core/register.html')
        else:
            society = None

        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=full_name,
                password=password,
                role=role,
                # All residents who register publicly are owners by default.
                # Rental profiles are created by owners from within their portal.
                resident_role='owner' if role == 'resident' else None,
                mobile_number=mobile,
                society_name=society,
                unit_number=unit_number,
            )
            return redirect(reverse('login') + '?registered=true')
        except IntegrityError:
            messages.error(request, 'An account with this email already exists.')
            return render(request, 'core/register.html')
    return render(request, 'core/register.html')

@login_required
def dashboard_redirect(request):
    if request.user.role == 'company':
        return redirect('company_dashboard')
    if request.user.role == 'admin' or request.user.role == 'secretary':
        return redirect('admin_dashboard')
    if request.user.role == 'watchman':
        return redirect('watchman_dashboard')
    return redirect('resident_dashboard')

@login_required
def placeholder_view(request, feature_name):
    if feature_name.lower() == "notices":
        return redirect('notices')
    return render(request, 'core/placeholder.html', {'feature_name': feature_name.capitalize()})

@login_required
def profile_view(request):
    return render(request, 'core/profile.html')

@login_required
def members_view(request):
    if request.user.role == 'company':
        # Get all invite codes generated by this company to list active societies
        from .models import InviteCode
        invite_codes = InviteCode.objects.filter(company=request.user)
        # Unique societies
        # Since each society gets 1 code, the invite_codes queryset IS the list of societies.
        return render(request, 'core/company_members.html', {'societies': invite_codes})
    
    else:
        # Residents and Secretaries see members of their own society
        society_name = request.user.society_name
        # Include resident owners and company role members in directory/dues tracking
        from django.db.models import Q
        members = User.objects.filter(
            Q(role='company') | Q(role='resident', resident_role='owner'),
            society_name=society_name
        )        
        # Calculate pending amounts for each member
        from resident.models import Bill
        from decimal import Decimal
        from datetime import date
        today = date.today()
        
        unpaid_members = []
        for member in members:
            # Shift from local calculation to the model's central logic
            total = member.get_maintenance_balance()
            
            member.pending_amount = total
            # We still need count of pending bills for UI if needed, but balance is the key
            member.pending_count = member.bills.filter(status='Pending').count()
            
            if total > 0:
                unpaid_members.append(member)
        
        from .models import InviteCode
        invite_obj = InviteCode.objects.filter(society_name=society_name).first()
        invite_code = invite_obj.code if invite_obj else None
        
        tab = request.GET.get('tab', 'all')
        
        return render(request, 'core/society_members.html', {
            'members': members if tab == 'all' else unpaid_members, 
            'unpaid_count': len(unpaid_members),
            'society_name': society_name,
            'invite_code': invite_code,
            'current_tab': tab
        })

@login_required
def pro_management(request):
    if request.user.role != 'secretary':
        return redirect('home')
        
    society_name = request.user.society_name
    members = User.objects.filter(society_name=society_name, role='resident')
    
    active_pro_count = members.filter(is_pro_member=True).count()
    
    from .models import Subscription
    active_sub = Subscription.objects.filter(
        society_name=society_name, 
        status='active'
    ).order_by('-end_date').first()
    
    limit = 250
    plan_name = "Trial / Basic"
    if active_sub:
        plan_name = dict(Subscription.PLAN_CHOICES).get(active_sub.plan_tier)
        if active_sub.plan_tier == '1-250':
            limit = 250
        elif active_sub.plan_tier == '251-500':
            limit = 500
        elif active_sub.plan_tier == '501+':
            limit = 999999
            
    return render(request, 'core/pro_management.html', {
        'members': members.order_by('username'),
        'active_pro_count': active_pro_count,
        'limit': limit,
        'limit_display': "Unlimited" if limit == 999999 else limit,
        'plan_name': plan_name,
        'society_name': society_name
    })

from django.views.decorators.csrf import csrf_exempt

@login_required
@csrf_exempt
def toggle_subscription_access(request, user_id):
    from django.http import JsonResponse
    if request.user.role != 'secretary':
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
        
    target_user = get_object_or_404(User, id=user_id, society_name=request.user.society_name)
    
    if not target_user.is_pro_member:
        from .models import Subscription
        active_sub = Subscription.objects.filter(
            society_name=request.user.society_name, 
            status='active'
        ).order_by('-end_date').first()
        
        limit = 250
        if active_sub:
            if active_sub.plan_tier == '1-250':
                limit = 250
            elif active_sub.plan_tier == '251-500':
                limit = 500
            elif active_sub.plan_tier == '501+':
                limit = 999999
        
        active_pro_count = User.objects.filter(society_name=request.user.society_name, is_pro_member=True, role='resident').count()
        if active_pro_count >= limit:
            return JsonResponse({'status': 'error', 'message': f'Subscription limit reached ({limit}). Please upgrade your plan.'})

    target_user.is_pro_member = not target_user.is_pro_member
    target_user.save()
    
    return JsonResponse({
        'status': 'success', 
        'is_pro': target_user.is_pro_member,
        'message': f"Access {'granted' if target_user.is_pro_member else 'revoked'} for {target_user.username}"
    })

@login_required
def notices_view(request):
    from .models import Notice
    society_name = request.user.society_name
    notices = Notice.objects.filter(society_name=society_name).order_by('-created_at')
    return render(request, 'core/notices.html', {'notices': notices})

def extract_ocr_details(image_file):
    """Helper to extract details using Google Gemini Flash (Vision)."""
    api_key = os.environ.get('GEMINI_API_KEY')
    
    if not api_key:
        print("❌ CRITICAL ERROR: GEMINI_API_KEY NOT FOUND IN ENV")
        return {'error': 'API Key Missing'}

    # Reset file pointer and read bytes
    image_file.seek(0)
    image_bytes = image_file.read()
    image_file.seek(0)

    print(f"🔍 AI Scanning Image... (Size: {len(image_bytes)} bytes)")
    
    try:
        from google.generativeai.types import HarmCategory, HarmBlockThreshold
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # Initialization is handled dynamically in the fallback section below
        
        # Prepare image (removed resizing to preserve small text for better OCR)
        img = Image.open(BytesIO(image_bytes))
        
        prompt = """
        ACT AS A RAW OCR ENGINE. Read every single detail from this UPI receipt.
        Return ONLY a JSON object with these EXACT keys:
        {
          "amount": number,
          "date": "DD/MM/YYYY",
          "txn_id": "string",
          "acc_digits": "string"
        }
        GUIDELINES:
        1. Date: If you see '29 Mar 2026', return '29/03/2026'.
        2. Amount: It's the number next to '₹'.
        3. Txn ID: Often labeled as 'Transaction ID' or 'UTR'.
        4. Acc Digits: Find 'Credited to' or 'XXXXX1234' and give the last 4 digits.
        5. DO NOT include any other text besides the JSON.
        """
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        # Prepare image correctly for Gemini
        img_data = {
            'mime_type': 'image/jpeg',
            'data': image_bytes
        }
        
        # ULTIMATE DYNAMIC FALLBACK: Find any model that works for this specific API Key
        try:
            # Get all models that support generating content
            available_models = [m for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            
            # Prioritize Flash if it exists in the list
            flash_models = [m for m in available_models if 'flash' in m.name.lower()]
            active_model_name = flash_models[0].name if flash_models else available_models[0].name
            
            print(f"🎯 Dynamic Model Selected: {active_model_name}")
            model = genai.GenerativeModel(active_model_name)
            response = model.generate_content([prompt, img_data], safety_settings=safety_settings)
        except Exception as e:
            return {'error': f'AI Scan Failed. Error: {str(e)}'}
        
        if not response.candidates or not response.candidates[0].content.parts:
            # Check for safety block
            finish_reason = response.candidates[0].finish_reason if response.candidates else "Unknown"
            return {'error': f'AI Blocked (Reason: {finish_reason}). Try a clearer screenshot.'}

        raw_text = response.text
        print(f"📄 Raw AI Text: {raw_text}")
        
        # 1. Try to get JSON from response
        clean_resp = raw_text.replace('```json', '').replace('```', '').strip()
        match = re.search(r'\{.*\}', clean_resp, re.DOTALL)
        data = json.loads(match.group(0)) if match else {}
        
        # 2. Extract with Fallbacks
        ext_amt = str(data.get('amount') or "")
        ext_date = str(data.get('date') or "")
        ext_txn = str(data.get('txn_id') or data.get('utr') or "")
        ext_acc = str(data.get('acc_digits') or "")

        # regex search in raw_text if JSON missed it
        if not ext_amt:
            amt_match = re.search(r'₹\s?(\d+(?:,\d+)*(?:\.\d+)?)', raw_text)
            if amt_match: ext_amt = amt_match.group(1)
            
        if not ext_date:
            date_match = re.search(r'(\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s\d{4})', raw_text, re.IGNORECASE)
            if date_match: ext_date = date_match.group(1)

        if not ext_txn:
            txn_match = re.search(r'(?:UTR|Transaction|Ref|Ref No)[\s:]*([A-Z0-9]{8,})', raw_text, re.IGNORECASE)
            if txn_match: ext_txn = txn_match.group(1)

        ext_acc = str(data.get('acc_digits') or "")
        if not ext_acc or ext_acc.lower() == 'none':
            acc_match = re.search(r'X{2,}(\d{4})', raw_text)
            ext_acc = acc_match.group(1) if acc_match else ""

        # Final check: If everything is blank, it's a failure
        if not ext_amt and not ext_date and not ext_txn:
             return {'error': 'AI could not detect any payment details in this image.'}

        return {
            'amount': ext_amt.replace('₹', '').replace(',', '').strip(),
            'date': ext_date.strip(),
            'txn_id': ext_txn.strip(),
            'acc_digits': ext_acc.strip()[-4:] if ext_acc else ""
        }
    except Exception as e:
        print(f"❌ Gemini OCR Error: {e}")
        return {'error': str(e)}

from django.views.decorators.csrf import csrf_exempt

@login_required
@csrf_exempt
def process_ocr_preview(request):
    """AJAX endpoint for OCR preview."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    image_file = request.FILES.get('proof_image')
    if not image_file:
        return JsonResponse({'success': False, 'error': 'No image uploaded'}, status=400)

    try:
        details = extract_ocr_details(image_file)
        if 'error' in details:
            print(f"⚠️ OCR Details Error: {details['error']}")
            return JsonResponse({'success': False, 'error': details['error']})
            
        return JsonResponse({
            'success': True,
            'amount': details.get('amount'),
            'date': details.get('date'),
            'txn_id': details.get('txn_id'),
            'acc_digits': details.get('acc_digits')
        })
    except Exception as e:
        print(f"❌ Process OCR Preview Exception: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def maintenance_view(request):
    from .models import InviteCode, PaymentProof, RentPaymentProof, SocietyMaintenanceSettings, RentalChargeSettings
    from django.utils import timezone
    from datetime import datetime
    
    is_rental = (request.user.role == 'resident' and request.user.resident_role == 'rental')
    society_name = request.user.society_name
    
    # Context Logic
    if is_rental:
        target_fee = request.user.get_rent_balance()
        proofs = RentPaymentProof.objects.filter(rental_user=request.user).order_by('-created_at')
        rental_charge = RentalChargeSettings.objects.filter(rental_user=request.user).first()
        settings_obj = rental_charge
    else:
        maintenance_settings = SocietyMaintenanceSettings.objects.filter(society_name=society_name).first()
        target_fee = request.user.get_maintenance_balance()
        proofs = (PaymentProof.objects.filter(society_name=society_name) if request.user.role == 'secretary' 
                  else PaymentProof.objects.filter(user=request.user)).order_by('-created_at')
        settings_obj = maintenance_settings

    if request.method == 'POST' and request.FILES.get('proof_image'):
        proof_file = request.FILES.get('proof_image')
        
        # Try to get details from POST (reviewed by user in frontend)
        manual_amount = request.POST.get('extracted_amount')
        manual_date_str = request.POST.get('extracted_date')
        manual_txn = request.POST.get('txn_id')

        if manual_amount and manual_date_str:
            amt_paid = Decimal(str(manual_amount).replace(',', '').strip() or '0.00')
            txn_id = manual_txn
            acc_digits = None  # We'll try to get this from a quick scan anyway if needed, or skip
            
            try:
                extracted_date = datetime.strptime(manual_date_str, "%d/%m/%Y").date()
            except:
                try: extracted_date = datetime.strptime(manual_date_str, "%Y-%m-%d").date()
                except: extracted_date = None
        else:
            # Fallback: OCR scan synchronously if not provided
            details = extract_ocr_details(proof_file)
            
            # Handle cases where amount might be None or empty string
            raw_amt = details.get('amount')
            if not raw_amt or str(raw_amt).strip().lower() == 'none':
                amt_paid = Decimal('0.00')
            else:
                amt_paid = Decimal(str(raw_amt).replace(',', '').strip())
            txn_id = details.get('txn_id')
            acc_digits = details.get('acc_digits')
            extracted_date = None
            
            if details.get('date'):
                try:
                    extracted_date = datetime.strptime(details['date'], "%d/%m/%Y").date()
                except:
                    try: extracted_date = datetime.strptime(details['date'], "%Y-%m-%d").date()
                    except: pass

        # 1. Unique Transaction ID Check (If AI found one)
        if txn_id:
            duplicate = PaymentProof.objects.filter(transaction_id=txn_id).exists() or \
                        RentPaymentProof.objects.filter(transaction_id=txn_id).exists()
            if duplicate:
                messages.error(request, f"Failure: Transaction ID '{txn_id}' has already been recorded.")
                return redirect('maintenance')

        # 2. Create the Proof object
        if is_rental:
            proof = RentPaymentProof.objects.create(
                rental_user=request.user, owner=request.user.owner, proof_image=proof_file,
                extracted_amount=amt_paid, transaction_id=txn_id, extracted_account_digits=acc_digits,
                extracted_date=extracted_date
            )
        else:
            eff_society = society_name or (request.user.owner.society_name if hasattr(request.user, 'owner') and request.user.owner else "Global")
            proof = PaymentProof.objects.create(
                user=request.user, society_name=eff_society, proof_image=proof_file,
                extracted_amount=amt_paid, transaction_id=txn_id, extracted_account_digits=acc_digits,
                extracted_date=extracted_date
            )
            
        # Comparison logic for Flagging
        is_flagged = False
        reasons = []
        
        expected_acc = None
        if is_rental:
            expected_acc = settings_obj.account_number[-4:] if settings_obj and settings_obj.account_number else None
        else:
            expected_acc = settings_obj.expected_payee_account if settings_obj else None

        if expected_acc and acc_digits and str(acc_digits) != str(expected_acc):
            is_flagged = True
            reasons.append(f"Account mismatch ({acc_digits})")
            
        if extracted_date and extracted_date != date.today():
             is_flagged = True
             reasons.append(f"Date mismatch")
        
        if is_flagged:
            proof.status = 'flagged'
            messages.warning(request, f"Proof uploaded but flagged for review: {', '.join(reasons)}.")
        else:
            proof.status = 'verified'
            messages.success(request, f"AI Scan successful! ₹{amt_paid} recorded and verified.")
            
        proof.save()
        return redirect('maintenance')

    return render(request, 'core/maintenance.html', {
        'proofs': proofs,
        'target_fee': target_fee,
        'settings': settings_obj,
        'is_rental': is_rental
    })

@login_required
def verify_payment_proof(request, proof_id, action):
    """Allows a Secretary, Admin, or Owner to manually approve or reject a payment proof."""
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    from .models import PaymentProof, RentPaymentProof
    
    # 1. Try to find as a Maintenance Proof (Secretary/Admin)
    proof = PaymentProof.objects.filter(id=proof_id).first()
    if proof:
        if request.user.role not in ['secretary', 'admin'] or proof.society_name != request.user.society_name:
            error_msg = "Permission denied for this maintenance proof."
            if is_ajax: return JsonResponse({'success': False, 'message': error_msg}, status=403)
            messages.error(request, error_msg)
            return redirect('maintenance')
    else:
        # 2. Try to find as a Rent Proof (Owner)
        proof = RentPaymentProof.objects.filter(id=proof_id, owner=request.user).first()
        if not proof:
            error_msg = "Proof not found or access denied."
            if is_ajax: return JsonResponse({'success': False, 'message': error_msg}, status=404)
            messages.error(request, error_msg)
            return redirect('maintenance')

    # Status Update Logic
    if action == 'approve':
        proof.status = 'approved'
        messages.success(request, f"Proof #{proof.id} has been manually approved.")
    elif action == 'reject':
        proof.status = 'rejected'
        messages.warning(request, f"Proof #{proof.id} has been rejected.")
    else:
        error_msg = "Invalid action requested."
        if is_ajax: return JsonResponse({'success': False, 'message': error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect('maintenance')
        
    proof.save()
    
    if is_ajax:
        return JsonResponse({
            'success': True, 
            'status': proof.status, 
            'message': f"Proof {action}ed successfully."
        })
        
    return redirect('maintenance')

@login_required
def delete_payment_proof(request, proof_id):
    from .models import PaymentProof, RentPaymentProof
    
    # Try to find in either table
    proof = PaymentProof.objects.filter(id=proof_id).first()
    is_rent_proof = False
    
    if not proof:
        proof = RentPaymentProof.objects.filter(id=proof_id).first()
        is_rent_proof = True
    
    if not proof:
        messages.error(request, "Proof not found.")
        return redirect('maintenance')
    
    # Permission Check
    can_delete = False
    if is_rent_proof:
        # For rent: only tenant or their owner
        if proof.rental_user == request.user or proof.owner == request.user:
            can_delete = True
    else:
        # For maintenance: only the user who uploaded or secretary
        if proof.user == request.user or request.user.role == 'secretary':
            can_delete = True

    if can_delete:
        proof.delete()
        messages.success(request, "Payment proof deleted successfully.")
    else:
        messages.error(request, "You do not have permission to delete this proof.")
        
    return redirect('maintenance')


@login_required
def generate_proof_receipt_pdf(request, proof_id):
    from .models import PaymentProof

    proof = PaymentProof.objects.filter(id=proof_id, user=request.user).first()

    if not proof:
        messages.error(request, "Receipt not found.")
        return redirect('maintenance')

    if proof.status not in ['verified', 'approved']:
        messages.error(request, "Receipt is only available for verified payments.")
        return redirect('maintenance')

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []
    title_style = ParagraphStyle('title', parent=styles['Title'], fontSize=18,
                                  textColor=colors.HexColor('#1a1a2e'), spaceAfter=6)
    story.append(Paragraph('PAYMENT PROOF RECEIPT', title_style))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e0e0e0')))
    story.append(Spacer(1, 0.4*cm))
    data = [
        ['Proof ID', f'PR-{proof.id}'],
        ['Resident', proof.user.get_full_name() or proof.user.username],
        ['Society', proof.society_name or '—'],
        ['Date Submitted', str(proof.created_at.date())],
        ['Transaction ID', proof.transaction_id or '—'],
        ['Amount', f'Rs. {proof.extracted_amount}'],
        ['Status', proof.status.upper()],
    ]
    table = Table(data, colWidths=[6*cm, 10*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#e0e0e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph('This is a system-generated receipt.', ParagraphStyle(
        'footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))
    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_proof_{proof.id}.pdf"'
    response.write(pdf)
    return response
@login_required
def generate_proof_receipt(request, proof_id):
    from .models import PaymentProof, RentPaymentProof
    
    # Try to find the proof in either model
    proof = PaymentProof.objects.filter(id=proof_id).first()
    if not proof:
        proof = RentPaymentProof.objects.filter(id=proof_id).first()
        
    if not proof:
        raise Http404("Payment proof not found.")

    # Permission Check
    can_view = False
    u_soc = (request.user.society_name or "").strip().lower()
    
    if request.user.role in ['secretary', 'admin']:
        # Admin/Secretary can view if it belongs to their society
        p_soc = ""
        if hasattr(proof, 'society_name'):
            p_soc = (proof.society_name or "").strip().lower()
        elif hasattr(proof, 'owner'):
            p_soc = (proof.owner.society_name or "").strip().lower()
            
        if p_soc == u_soc and u_soc != "":
            can_view = True
    elif hasattr(proof, 'user') and proof.user == request.user:
        can_view = True
    elif hasattr(proof, 'rental_user') and proof.rental_user == request.user:
        can_view = True
        
    if not can_view:
        messages.error(request, "Permission denied.")
        return redirect('maintenance')

    if proof.status not in ['verified', 'approved']:
        messages.error(request, "Receipt is only available for verified/approved payments.")
        return redirect('maintenance')

    user_for_receipt = getattr(proof, 'user', getattr(proof, 'rental_user', None))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []
    title_style = ParagraphStyle('title', parent=styles['Title'], fontSize=18,
                                  textColor=colors.HexColor('#1a1a2e'), spaceAfter=6)
    story.append(Paragraph('PAYMENT RECEIPT', title_style))
    story.append(Paragraph(f'Proof #{proof.id}', ParagraphStyle('sub', parent=styles['Normal'],
                                                                  fontSize=10, textColor=colors.black, spaceAfter=12)))
    story.append(HRFlowable(width='100%', thickness=1.5, color=colors.black))
    story.append(Spacer(1, 0.4*cm))
    data = [
        ['Resident', user_for_receipt.get_full_name() or user_for_receipt.username],
        ['Society', user_for_receipt.society_name or '—'],
        ['Unit No.', user_for_receipt.unit_number or '—'],
        ['Month', proof.created_at.strftime('%B %Y')],
        ['Transaction ID', proof.transaction_id or 'SOCIETY_INTERNAL'],
        ['Amount Paid', f'Rs. {proof.extracted_amount or "0.00"}'],
        ['Status', 'Verified'],
        ['Date', str(proof.extracted_date or proof.created_at.date())],
    ]
    table = Table(data, colWidths=[6*cm, 10*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.8*cm))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e0e0e0')))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph('This is a system-generated receipt.', ParagraphStyle(
        'footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))
    doc.build(story, onFirstPage=add_pdf_watermark, onLaterPages=add_pdf_watermark)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{proof.id}.pdf"'
    response.write(pdf)
    return response



@login_required
def watchman_dashboard(request):
    if request.user.role != 'watchman':
        return redirect('home')
    
    from admin_panel.models import Visitor
    from django.contrib import messages
    
    if request.method == 'POST':
        name = request.POST.get('name')
        unit = request.POST.get('unit')
        vehicle_number = request.POST.get('vehicle_number')
        if vehicle_number:
            vehicle_number = vehicle_number.upper()
        visitor_photo = request.FILES.get('visitor_photo')
        vehicle_photo = request.FILES.get('vehicle_photo')
        watchman_name = request.POST.get('watchman_name', request.user.get_full_name() or request.user.username)
        
        Visitor.objects.create(
            name=name,
            unit=unit,
            vehicle_number=vehicle_number,
            visitor_photo=visitor_photo,
            vehicle_photo=vehicle_photo,
            recorded_by=watchman_name,
            status='Inside'
        )
        messages.success(request, f"Entry recorded for {name} (Unit {unit})")
        return redirect('watchman_dashboard')
    
    # Show last 10 visitors
    # Here we filter by society if unit or recorded_by helps identify the society
    # For now, we take all but in a real app we'd scope this by society_name
    past_visitors = Visitor.objects.all().order_by('-time_in')[:10]
    return render(request, 'core/watchman_dashboard.html', {'past_visitors': past_visitors})

@login_required
def gate_records(request):
    if request.user.role != 'watchman':
        return redirect('home')
    from admin_panel.models import Visitor
    all_visitors = Visitor.objects.all().order_by('-time_in')
    return render(request, 'core/gate_records.html', {'visitors': all_visitors})

@login_required
def subscription_view(request):
    if request.user.role != 'secretary':
        return redirect('home')
    
    from .models import Subscription
    from django.utils import timezone
    from dateutil.relativedelta import relativedelta
    from decimal import Decimal
    
    # Active or Pending subscription for this society
    subscription = Subscription.objects.filter(
        society_name=request.user.society_name, 
        status__in=['active', 'pending', 'review']
    ).order_by('-start_date').first()

    # Check if the active one has expired
    if subscription and subscription.status == 'active' and subscription.end_date < timezone.now():
        subscription.status = 'expired'
        subscription.is_active = False
        subscription.save()
        subscription = None

    qr_base64 = None
    if subscription and subscription.status == 'pending':
        import qrcode
        import base64
        from io import BytesIO
        
        upi_id = "shriraj1223shetty-1@okhdfcbank"
        upi_name = "Shriraj Shetty"
        upi_link = f"upi://pay?pa={upi_id}&pn={upi_name}&am={subscription.amount}&cu=INR&tn=Society Subscription"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(upi_link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'select_plan':
            flats_count = int(request.POST.get('flats_count', 0))
            duration = int(request.POST.get('duration', 1))
            
            # Determine tier and rate
            if flats_count <= 250:
                if duration == 1: rate = 55
                elif duration == 6: rate = 45
                else: rate = 40
                tier = '1-250'
            elif flats_count <= 500:
                if duration == 1: rate = 45
                elif duration == 6: rate = 35
                else: rate = 30
                tier = '251-500'
            else:
                if duration == 1: rate = 35
                elif duration == 6: rate = 25
                else: rate = 20
                tier = '501+'
                
            total_amount = Decimal(flats_count) * Decimal(rate) * Decimal(duration)
            
            # Cleanup existing pending/review subs
            Subscription.objects.filter(
                society_name=request.user.society_name, 
                status__in=['pending', 'review']
            ).delete()
            
            # Create new subscription
            end_date = timezone.now() + relativedelta(months=duration)
            new_sub = Subscription.objects.create(
                society_name=request.user.society_name or "Individual",
                secretary_id=request.user.id,
                plan_tier=tier,
                duration_months=duration,
                amount=total_amount,
                end_date=end_date,
                status='pending',
                is_active=False
            )
            return redirect(reverse('subscription_view') + '?pay=true')

        elif action == 'upload_proof':
            proof_file = request.FILES.get('payment_proof')
            sub_id = request.POST.get('subscription_id')
            sub = get_object_or_404(Subscription, id=sub_id, secretary_id=request.user.id)
            
            if proof_file:
                sub.payment_proof = proof_file
                sub.status = 'review'
                sub.save()
                messages.success(request, "Payment proof uploaded! Your subscription will be activated once verified.")
            return redirect('subscription_view')

    return render(request, 'core/subscription.html', {
        'active_subscription': subscription,
        'show_payment_modal': request.GET.get('pay') == 'true',
        'qr_code': qr_base64
    })

@login_required
def download_unpaid_report(request):
    if request.user.role != 'secretary':
        return redirect('home')

    society_name = request.user.society_name
    # Include resident owners and company role members in the maintenance report
    from django.db.models import Q
    members = User.objects.filter(
        Q(role='company') | Q(role='resident', resident_role='owner'),
        society_name=society_name
    )
    
    from resident.models import Bill
    from decimal import Decimal
    from datetime import date
    today = date.today()
    
    unpaid_data = []
    total_unpaid = Decimal('0.00')

    for member in members:
        member_total = member.get_maintenance_balance()
        
        if member_total > 0:
            unpaid_data.append([
                member.unit_number or '—',
                member.get_full_name() or member.username,
                member.mobile_number or '—',
                f"Rs. {member_total}"
            ])
            total_unpaid += member_total

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle('title', parent=styles['Title'], fontSize=18,
                                  textColor=colors.HexColor('#1a1a2e'), spaceAfter=12)
    story.append(Paragraph('MAINTENANCE DUES REPORT', title_style))
    story.append(Paragraph(f'Society: {society_name}', styles['Normal']))
    story.append(Paragraph(f'Date: {today.strftime("%d %B %Y")}', styles['Normal']))
    story.append(Spacer(1, 0.5*cm))

    # Table
    header = ['Unit No.', 'Name', 'Mobile', 'Amount Due']
    table_data = [header] + unpaid_data
    
    # Add Summary Row
    table_data.append(['', 'TOTAL DUES', '', f'Rs. {total_unpaid}'])

    table = Table(table_data, colWidths=[3*cm, 7*cm, 4*cm, 4*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#fafafa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(table)

    story.append(Spacer(1, 1*cm))
    story.append(Paragraph('This is a system-generated summary of pending maintenance dues.', 
                           ParagraphStyle('footer', parent=styles['Normal'], fontSize=8, 
                                          textColor=colors.grey, alignment=TA_CENTER)))

    doc.build(story, onFirstPage=add_pdf_watermark, onLaterPages=add_pdf_watermark)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="unpaid_report_{today}.pdf"'
    response.write(pdf)
    return response


