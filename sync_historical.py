import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "manager_django.settings")
django.setup()

from core.models import Expense, PaymentProof, JournalEntry, JournalItem, LedgerAccount

def get_default_accounts(society_name):
    bank, _ = LedgerAccount.objects.get_or_create(society_name=society_name, name='Bank Account', defaults={'account_type': 'Asset', 'statement_type': 'BalanceSheet'})
    maintenance, _ = LedgerAccount.objects.get_or_create(society_name=society_name, name='Maintenance Income', defaults={'account_type': 'Revenue', 'statement_type': 'PL'})
    expense_acc, _ = LedgerAccount.objects.get_or_create(society_name=society_name, name='General Expenses', defaults={'account_type': 'Expense', 'statement_type': 'PL'})
    return bank, maintenance, expense_acc

# Migrate Expenses
for expense in Expense.objects.all():
    ref_desc = f"New Expense: {expense.payee_name} [REF:EXP-{expense.id}]"
    if not JournalEntry.objects.filter(description=ref_desc).exists():
        bank, _, expense_acc = get_default_accounts(expense.society_name)
        entry = JournalEntry.objects.create(society_name=expense.society_name, description=ref_desc)
        JournalItem.objects.create(entry=entry, account=expense_acc, amount=expense.amount, entry_type='Dr')
        JournalItem.objects.create(entry=entry, account=bank, amount=expense.amount, entry_type='Cr')

# Migrate Payment Proofs
for proof in PaymentProof.objects.filter(status__in=['verified', 'approved']):
    ref_desc = f"Maintenance Receipt [REF:PAY-{proof.id}]"
    if not JournalEntry.objects.filter(description__endswith=ref_desc).exists():
        bank, maintenance, _ = get_default_accounts(proof.society_name)
        amount = proof.extracted_amount if proof.extracted_amount else 0
        if amount > 0:
            entry = JournalEntry.objects.create(society_name=proof.society_name, description=ref_desc)
            JournalItem.objects.create(entry=entry, account=bank, amount=amount, entry_type='Dr')
            JournalItem.objects.create(entry=entry, account=maintenance, amount=amount, entry_type='Cr')

print("Successfully backfilled historical cashbook data into Ledger Accounts!")
