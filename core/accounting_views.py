from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import LedgerAccount, JournalEntry, JournalItem
from django.db.models import Sum
from django.utils import timezone
from core.models import InviteCode

def get_accounting_society(request):
    if request.user.role == 'company':
        return request.GET.get('society')
    return request.user.society_name

@login_required
def accounting_dashboard(request):
    society_name = get_accounting_society(request)
    
    if request.user.role == 'company' and not society_name:
        # Show a list of societies to the company to pick from
        society_names = InviteCode.objects.filter(company=request.user).values_list('society_name', flat=True).distinct()
        return render(request, 'core/accounting/company_society_select.html', {'societies': society_names})
        
    recent_entries = JournalEntry.objects.filter(society_name=society_name).order_by('-created_at')[:20]
    accounts_count = LedgerAccount.objects.filter(society_name=society_name).count()
    
    return render(request, 'core/accounting/dashboard.html', {
        'society_name': society_name,
        'recent_entries': recent_entries,
        'accounts_count': accounts_count
    })

@login_required
def setup_default_accounts(request):
    society_name = get_accounting_society(request)
    if not society_name:
        return redirect('accounting_dashboard')
        
    defaults = [
        # Trading Dr
        ('Opening Stock', 'Asset', 'Trading'),
        ('Purchases', 'Expense', 'Trading'),
        ('Wages', 'Expense', 'Trading'),
        ('Direct Expenses', 'Expense', 'Trading'),
        ('Freight & Carriage Inward', 'Expense', 'Trading'),
        ('Custom Duty', 'Expense', 'Trading'),
        ('Coal, Gas, Fuel etc.', 'Expense', 'Trading'),
        ('Royalties', 'Expense', 'Trading'),
        ('Factory expenses', 'Expense', 'Trading'),
        # Trading Cr
        ('Sales', 'Revenue', 'Trading'),
        ('Closing Stock', 'Asset', 'Trading'),
        
        # P&L Dr
        ('Salaries & Wages', 'Expense', 'PL'),
        ('Rent Rates & Taxes', 'Expense', 'PL'),
        ('Insurance', 'Expense', 'PL'),
        ('Bank Charges', 'Expense', 'PL'),
        ('Discount Allowed', 'Expense', 'PL'),
        ('Audit fees', 'Expense', 'PL'),
        ('Depreciation', 'Expense', 'PL'),
        ('Travelling expenses', 'Expense', 'PL'),
        ('Advertisement', 'Expense', 'PL'),
        ('Printing & Stationery', 'Expense', 'PL'),
        ('Interest Paid', 'Expense', 'PL'),
        ('General Expenses', 'Expense', 'PL'),
        # P&L Cr
        ('Rent received', 'Revenue', 'PL'),
        ('Commission received', 'Revenue', 'PL'),
        ('Interest on Investment', 'Revenue', 'PL'),
        ('Discount received', 'Revenue', 'PL'),
        
        # Balance Sheet Assets
        ('Cash in hand', 'Asset', 'BalanceSheet'),
        ('Bank Account', 'Asset', 'BalanceSheet'),
        ('Bills Receivable', 'Asset', 'BalanceSheet'),
        ('Sundry Debtors', 'Asset', 'BalanceSheet'),
        ('Goodwill', 'Asset', 'BalanceSheet'),
        ('Furniture', 'Asset', 'BalanceSheet'),
        ('Plant & Machinery', 'Asset', 'BalanceSheet'),
        ('Land & Building', 'Asset', 'BalanceSheet'),
        ('Prepaid expenses', 'Asset', 'BalanceSheet'),
        # Balance Sheet Liab
        ('Capital', 'Equity', 'BalanceSheet'),
        ('Drawings', 'Equity', 'BalanceSheet'),
        ('Bank Loan', 'Liability', 'BalanceSheet'),
        ('Sundry Creditors', 'Liability', 'BalanceSheet'),
        ('Bills Payable', 'Liability', 'BalanceSheet'),
    ]
    
    for name, acc_type, stmt_type in defaults:
        LedgerAccount.objects.get_or_create(
            society_name=society_name,
            name=name,
            defaults={'account_type': acc_type, 'statement_type': stmt_type}
        )
        
    url = '/accounting/'
    if request.user.role == 'company' and request.GET.get('society'):
        url += f"?society={request.GET.get('society')}"
    return redirect(url)


@login_required
def delete_journal_entry(request, entry_id):
    society_name = get_accounting_society(request)
    if not society_name:
        return redirect('home')
        
    entry = JournalEntry.objects.filter(id=entry_id, society_name=society_name).first()
    if entry:
        entry.delete()
        
    url = '/accounting/'
    if request.user.role == 'company' and request.GET.get('society'):
        url += f"?society={request.GET.get('society')}"
    return redirect(url)

@login_required
def add_journal_entry(request):
    society_name = get_accounting_society(request)
    if request.user.role == 'company' and not society_name:
        return redirect('accounting_dashboard')
    if request.method == 'POST':
        date = request.POST.get('date')
        description = request.POST.get('description')
        
        dr_account_id = request.POST.get('dr_account')
        cr_account_id = request.POST.get('cr_account')
        amount = request.POST.get('amount')
        
        dr_account = LedgerAccount.objects.get(id=dr_account_id, society_name=society_name)
        cr_account = LedgerAccount.objects.get(id=cr_account_id, society_name=society_name)
        
        entry = JournalEntry.objects.create(
            society_name=society_name,
            date=date,
            description=description
        )
        
        JournalItem.objects.create(entry=entry, account=dr_account, amount=amount, entry_type='Dr')
        JournalItem.objects.create(entry=entry, account=cr_account, amount=amount, entry_type='Cr')
        
        return redirect('accounting_dashboard')
        
    accounts = LedgerAccount.objects.filter(society_name=society_name)
    return render(request, 'core/accounting/add_entry.html', {'accounts': accounts})

def calculate_account_balance(account):
    dr_total = account.journalitem_set.filter(entry_type='Dr').aggregate(Sum('amount'))['amount__sum'] or 0
    cr_total = account.journalitem_set.filter(entry_type='Cr').aggregate(Sum('amount'))['amount__sum'] or 0
    
    if account.account_type in ['Asset', 'Expense']:
        diff = dr_total - cr_total
        return abs(diff), 'Dr' if diff >= 0 else 'Cr'
    else:
        diff = cr_total - dr_total
        return abs(diff), 'Cr' if diff >= 0 else 'Dr'

@login_required
def trial_balance(request):
    society_name = get_accounting_society(request)
    if request.user.role == 'company' and not society_name:
        return redirect('accounting_dashboard')
        
    accounts = LedgerAccount.objects.filter(society_name=society_name)
    
    tb_data = []
    total_dr = 0
    total_cr = 0
    
    for acc in accounts:
        bal, bal_type = calculate_account_balance(acc)
        if bal != 0:
            if bal_type == 'Dr':
                tb_data.append({'id': acc.id, 'name': acc.name, 'dr': bal, 'cr': 0})
                total_dr += bal
            else:
                tb_data.append({'id': acc.id, 'name': acc.name, 'dr': 0, 'cr': bal})
                total_cr += bal
                
    return render(request, 'core/accounting/trial_balance.html', {
        'tb_data': tb_data,
        'total_dr': total_dr,
        'total_cr': total_cr,
        'society_name': society_name
    })

@login_required
def account_ledger(request, account_id):
    society_name = get_accounting_society(request)
    if not society_name:
        return redirect('accounting_dashboard')
        
    account = get_object_or_404(LedgerAccount, id=account_id, society_name=society_name)
    items = JournalItem.objects.filter(account=account).select_related('entry').order_by('entry__date', 'entry__created_at')
    
    # Calculate running balance
    ledger_entries = []
    running_balance = 0
    for item in items:
        if account.account_type in ['Asset', 'Expense']:
            if item.entry_type == 'Dr':
                running_balance += item.amount
            else:
                running_balance -= item.amount
        else:
            if item.entry_type == 'Cr':
                running_balance += item.amount
            else:
                running_balance -= item.amount
        
        ledger_entries.append({
            'date': item.entry.date,
            'description': item.entry.description,
            'entry_type': item.entry_type,
            'amount': item.amount,
            'balance': running_balance
        })

    return render(request, 'core/accounting/account_ledger.html', {
        'account': account,
        'ledger_entries': ledger_entries,
        'society_name': society_name
    })


@login_required
def final_accounts(request):
    society_name = get_accounting_society(request)
    if request.user.role == 'company' and not society_name:
        return redirect('accounting_dashboard')
        
    accounts = LedgerAccount.objects.filter(society_name=society_name)
    
    trading_dr = []
    trading_cr = []
    pl_dr = []
    pl_cr = []
    bs_assets = []
    bs_liab = []
    
    trading_dr_total = 0
    trading_cr_total = 0
    pl_dr_total = 0
    pl_cr_total = 0
    bs_assets_total = 0
    bs_liab_total = 0
    
    for acc in accounts:
        bal, bal_type = calculate_account_balance(acc)
        if bal == 0:
            continue
            
        if acc.statement_type == 'Trading':
            if bal_type == 'Dr':
                trading_dr.append({'name': acc.name, 'amount': bal})
                trading_dr_total += bal
            else:
                trading_cr.append({'name': acc.name, 'amount': bal})
                trading_cr_total += bal
        elif acc.statement_type == 'PL':
            if bal_type == 'Dr':
                pl_dr.append({'name': acc.name, 'amount': bal})
                pl_dr_total += bal
            else:
                pl_cr.append({'name': acc.name, 'amount': bal})
                pl_cr_total += bal
        elif acc.statement_type == 'BalanceSheet':
            if acc.account_type == 'Asset':
                # Assets should normally have a Dr balance. If they have Cr, it might be a contra, but we'll show it as negative asset for simplicity or just put it in liabilities.
                if bal_type == 'Dr':
                    bs_assets.append({'name': acc.name, 'amount': bal})
                    bs_assets_total += bal
            elif acc.account_type in ['Liability', 'Equity']:
                if bal_type == 'Cr':
                    bs_liab.append({'name': acc.name, 'amount': bal})
                    bs_liab_total += bal

    # Calculate Gross Profit / Loss
    gross_diff = trading_cr_total - trading_dr_total
    gross_profit = max(0, gross_diff)
    gross_loss = max(0, -gross_diff)

    if gross_profit > 0:
        trading_dr.append({'name': 'Gross Profit c/d', 'amount': gross_profit})
        trading_dr_total += gross_profit
        pl_cr.append({'name': 'Gross Profit b/d', 'amount': gross_profit})
        pl_cr_total += gross_profit
    elif gross_loss > 0:
        trading_cr.append({'name': 'Gross Loss c/d', 'amount': gross_loss})
        trading_cr_total += gross_loss
        pl_dr.append({'name': 'Gross Loss b/d', 'amount': gross_loss})
        pl_dr_total += gross_loss

    # Calculate Net Profit / Loss
    net_diff = pl_cr_total - pl_dr_total
    net_profit = max(0, net_diff)
    net_loss = max(0, -net_diff)

    if net_profit > 0:
        pl_dr.append({'name': 'Net Profit (transferred to Capital)', 'amount': net_profit})
        pl_dr_total += net_profit
        bs_liab.append({'name': 'Net Profit', 'amount': net_profit})
        bs_liab_total += net_profit
    elif net_loss > 0:
        pl_cr.append({'name': 'Net Loss (transferred from Capital)', 'amount': net_loss})
        pl_cr_total += net_loss
        bs_assets.append({'name': 'Net Loss', 'amount': net_loss})
        bs_assets_total += net_loss
        
    return render(request, 'core/accounting/final_accounts.html', {
        'trading_dr': trading_dr, 'trading_cr': trading_cr,
        'trading_dr_total': trading_dr_total, 'trading_cr_total': trading_cr_total,
        'gross_profit': gross_profit, 'gross_loss': gross_loss,
        'pl_dr': pl_dr, 'pl_cr': pl_cr,
        'pl_dr_total': pl_dr_total, 'pl_cr_total': pl_cr_total,
        'net_profit': net_profit, 'net_loss': net_loss,
        'bs_assets': bs_assets, 'bs_liabilities': bs_liab,
        'bs_assets_total': bs_assets_total, 'bs_liab_total': bs_liab_total,
        'society_name': society_name
    })

from django.http import HttpResponse
from datetime import date

def get_accounting_data(society_name):
    from .models import LedgerAccount, JournalEntry
    accounts = LedgerAccount.objects.filter(society_name=society_name)
    
    tb_data = []
    total_dr = total_cr = 0
    
    trading_dr = []; trading_cr = []
    trading_dr_total = trading_cr_total = 0
    
    pl_dr = []; pl_cr = []
    pl_dr_total = pl_cr_total = 0
    
    bs_assets = []; bs_liabilities = []
    bs_assets_total = bs_liab_total = 0
    
    for acc in accounts:
        bal = acc.get_balance()
        if bal == 0: continue
            
        bal_type = 'Dr' if bal > 0 else 'Cr'
        bal = abs(bal)
        
        tb_data.append({'name': acc.name, 'dr': bal if bal_type == 'Dr' else 0, 'cr': bal if bal_type == 'Cr' else 0})
        if bal_type == 'Dr': total_dr += bal
        else: total_cr += bal
        
        if acc.statement_type == 'Trading':
            if bal_type == 'Dr':
                trading_dr.append({'name': acc.name, 'amount': bal})
                trading_dr_total += bal
            else:
                trading_cr.append({'name': acc.name, 'amount': bal})
                trading_cr_total += bal
        elif acc.statement_type == 'PL':
            if bal_type == 'Dr':
                pl_dr.append({'name': acc.name, 'amount': bal})
                pl_dr_total += bal
            else:
                pl_cr.append({'name': acc.name, 'amount': bal})
                pl_cr_total += bal
        elif acc.statement_type == 'BalanceSheet':
            if bal_type == 'Dr':
                bs_assets.append({'name': acc.name, 'amount': bal})
                bs_assets_total += bal
            else:
                bs_liabilities.append({'name': acc.name, 'amount': bal})
                bs_liab_total += bal

    gross_profit = max(0, trading_cr_total - trading_dr_total)
    gross_loss = max(0, trading_dr_total - trading_cr_total)
    
    pl_cr_total_adjusted = pl_cr_total + gross_profit
    pl_dr_total_adjusted = pl_dr_total + gross_loss
    
    net_profit = max(0, pl_cr_total_adjusted - pl_dr_total_adjusted)
    net_loss = max(0, pl_dr_total_adjusted - pl_cr_total_adjusted)
    
    journal_entries = JournalEntry.objects.filter(society_name=society_name).order_by('date', 'id').prefetch_related('items__account')

    return {
        'journal_entries': journal_entries,
        'tb_data': tb_data, 'total_dr': total_dr, 'total_cr': total_cr,
        'trading_dr': trading_dr, 'trading_cr': trading_cr,
        'trading_dr_total': trading_dr_total, 'trading_cr_total': trading_cr_total,
        'gross_profit': gross_profit, 'gross_loss': gross_loss,
        'pl_dr': pl_dr, 'pl_cr': pl_cr,
        'pl_dr_total': pl_dr_total, 'pl_cr_total': pl_cr_total,
        'net_profit': net_profit, 'net_loss': net_loss,
        'bs_assets': bs_assets, 'bs_liabilities': bs_liabilities,
        'bs_assets_total': bs_assets_total, 'bs_liab_total': bs_liab_total,
        'society_name': society_name
    }

@login_required
def full_accounting_report(request):
    if request.user.role not in ['secretary', 'company']:
        return redirect('home')
    society_name = request.user.society_name or request.GET.get('society')
    data = get_accounting_data(society_name)
    data['download_signature'] = get_report_signature(society_name)
    return render(request, 'core/accounting/full_report.html', data)

import hashlib
from django.conf import settings

def get_report_signature(society_name):
    """Generates a secure signature for a society report to allow public but protected access."""
    secret = settings.SECRET_KEY
    return hashlib.sha256(f"{society_name}{secret}".encode()).hexdigest()

@login_required
def download_report_pdf(request):
    """Server-side PDF generation for APK/Mobile compatibility."""
    if request.user.role not in ['secretary', 'company']:
        return HttpResponse("Unauthorized", status=403)
        
    society_name = request.user.society_name or request.GET.get('society')
    return _generate_accounting_pdf(society_name)

def public_download_report_pdf(request, society_name, signature):
    """Allows downloading a society report without login IF the signature is valid.
    Fixes Android WebView session issues."""
    if signature != get_report_signature(society_name):
        return HttpResponse("Invalid Signature", status=403)
        
    return _generate_accounting_pdf(society_name)

def _generate_accounting_pdf(society_name):
    """Shared internal logic to generate the full accounting PDF."""
    data = get_accounting_data(society_name)
    
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from .views import add_pdf_watermark
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Header
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=18, spaceAfter=20)
    story.append(Paragraph(f"Financial Report - {society_name}", title_style))
    story.append(Paragraph(f"Year: 2023-24 | Generated: {date.today()}", styles['Normal']))
    story.append(Spacer(1, 1*cm))
    
    # 1. Journal Register
    story.append(Paragraph("1. Journal Register", styles['Heading2']))
    journal_data = [['Date', 'Description', 'Account', 'Dr', 'Cr']]
    for entry in data['journal_entries']:
        for item in entry.items.all():
            journal_data.append([
                entry.date.strftime('%d-%m-%Y') if hasattr(entry.date, 'strftime') else str(entry.date),
                entry.description,
                item.account.name,
                f"{item.amount:.2f}" if item.entry_type == 'Dr' else '',
                f"{item.amount:.2f}" if item.entry_type == 'Cr' else ''
            ])
    
    jt = Table(journal_data, colWidths=[2.5*cm, 6*cm, 5*cm, 2*cm, 2*cm])
    jt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    story.append(jt)
    story.append(PageBreak())

    # 2. Trial Balance
    story.append(Paragraph("2. Trial Balance", styles['Heading2']))
    tb_table_data = [['Particulars', 'Debit (Rs)', 'Credit (Rs)']]
    for row in data['tb_data']:
        tb_table_data.append([row['name'], f"{row['dr']:.2f}" if row['dr'] else '0.00', f"{row['cr']:.2f}" if row['cr'] else '0.00'])
    tb_table_data.append(['Total', f"{data['total_dr']:.2f}", f"{data['total_cr']:.2f}"])
    
    t = Table(tb_table_data, colWidths=[10*cm, 4*cm, 4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    story.append(t)
    story.append(PageBreak())
    
    # 3. Trading Account
    story.append(Paragraph("3. Trading Account", styles['Heading2']))
    trading_data = [['Debit Particulars', 'Amount', 'Credit Particulars', 'Amount']]
    max_t = max(len(data['trading_dr']), len(data['trading_cr']))
    for i in range(max_t):
        dr = data['trading_dr'][i] if i < len(data['trading_dr']) else {'name': '', 'amount': ''}
        cr = data['trading_cr'][i] if i < len(data['trading_cr']) else {'name': '', 'amount': ''}
        trading_data.append([dr['name'], dr['amount'], cr['name'], cr['amount']])
    
    t_table = Table(trading_data, colWidths=[5*cm, 3*cm, 5*cm, 3*cm])
    t_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('ALIGN', (3,0), (3,-1), 'RIGHT'),
    ]))
    story.append(t_table)
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(f"Gross Profit: Rs. {data['gross_profit']:.2f}", styles['Normal']))
    story.append(PageBreak())

    # 4. Profit & Loss Account
    story.append(Paragraph("4. Profit & Loss Account", styles['Heading2']))
    pl_data = [['Debit (Expenses)', 'Amount', 'Credit (Incomes)', 'Amount']]
    max_pl = max(len(data['pl_dr']), len(data['pl_cr']))
    for i in range(max_pl):
        dr = data['pl_dr'][i] if i < len(data['pl_dr']) else {'name': '', 'amount': ''}
        cr = data['pl_cr'][i] if i < len(data['pl_cr']) else {'name': '', 'amount': ''}
        pl_data.append([dr['name'], dr['amount'], cr['name'], cr['amount']])
    
    pl_table = Table(pl_data, colWidths=[5*cm, 3*cm, 5*cm, 3*cm])
    pl_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('ALIGN', (3,0), (3,-1), 'RIGHT'),
    ]))
    story.append(pl_table)
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(f"Net Profit: Rs. {data['net_profit']:.2f}", styles['Normal']))
    story.append(PageBreak())

    # 5. Balance Sheet
    story.append(Paragraph("5. Balance Sheet", styles['Heading2']))
    bs_data = [['Liabilities', 'Amount', 'Assets', 'Amount']]
    max_bs = max(len(data['bs_liabilities']), len(data['bs_assets']))
    for i in range(max_bs):
        liab = data['bs_liabilities'][i] if i < len(data['bs_liabilities']) else {'name': '', 'amount': ''}
        asset = data['bs_assets'][i] if i < len(data['bs_assets']) else {'name': '', 'amount': ''}
        bs_data.append([liab['name'], liab['amount'], asset['name'], asset['amount']])
    
    bs_table = Table(bs_data, colWidths=[5*cm, 3*cm, 5*cm, 3*cm])
    bs_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.whitesmoke),
    ]))
    story.append(bs_table)
    
    doc.build(story, onFirstPage=add_pdf_watermark, onLaterPages=add_pdf_watermark)
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Full_Report_{society_name}.pdf"'
    response.write(buffer.getvalue())
    return response
