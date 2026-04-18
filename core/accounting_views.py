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
    return render(request, 'core/accounting/dashboard.html', {
        'society_name': society_name,
        'recent_entries': recent_entries
    })

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
        return dr_total - cr_total, 'Dr' if dr_total >= cr_total else 'Cr'
    else:
        return cr_total - dr_total, 'Cr' if cr_total >= dr_total else 'Dr'

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
                tb_data.append({'name': acc.name, 'dr': bal, 'cr': 0})
                total_dr += bal
            else:
                tb_data.append({'name': acc.name, 'dr': 0, 'cr': bal})
                total_cr += bal
                
    return render(request, 'core/accounting/trial_balance.html', {
        'tb_data': tb_data,
        'total_dr': total_dr,
        'total_cr': total_cr
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
    gross_profit = trading_cr_total - trading_dr_total
    if gross_profit > 0:
        trading_dr.append({'name': 'Gross Profit c/d', 'amount': gross_profit})
        trading_dr_total += gross_profit
        pl_cr.append({'name': 'Gross Profit b/d', 'amount': gross_profit})
        pl_cr_total += gross_profit
    elif gross_profit < 0:
        trading_cr.append({'name': 'Gross Loss c/d', 'amount': abs(gross_profit)})
        trading_cr_total += abs(gross_profit)
        pl_dr.append({'name': 'Gross Loss b/d', 'amount': abs(gross_profit)})
        pl_dr_total += abs(gross_profit)

    # Calculate Net Profit / Loss
    net_profit = pl_cr_total - pl_dr_total
    if net_profit > 0:
        pl_dr.append({'name': 'Net Profit (transferred to Capital)', 'amount': net_profit})
        pl_dr_total += net_profit
        bs_liab.append({'name': 'Net Profit', 'amount': net_profit})
        bs_liab_total += net_profit
    elif net_profit < 0:
        pl_cr.append({'name': 'Net Loss (transferred from Capital)', 'amount': abs(net_profit)})
        pl_cr_total += abs(net_profit)
        bs_assets.append({'name': 'Net Loss', 'amount': abs(net_profit)})
        bs_assets_total += abs(net_profit)
        
    return render(request, 'core/accounting/final_accounts.html', {
        'trading_dr': trading_dr, 'trading_cr': trading_cr,
        'trading_dr_total': trading_dr_total, 'trading_cr_total': trading_cr_total,
        
        'pl_dr': pl_dr, 'pl_cr': pl_cr,
        'pl_dr_total': pl_dr_total, 'pl_cr_total': pl_cr_total,
        
        'bs_assets': bs_assets, 'bs_liab': bs_liab,
        'bs_assets_total': bs_assets_total, 'bs_liab_total': bs_liab_total
    })
