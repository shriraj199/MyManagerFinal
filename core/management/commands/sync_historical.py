from django.core.management.base import BaseCommand
from core.models import Expense, PaymentProof, JournalEntry, JournalItem, LedgerAccount

class Command(BaseCommand):
    help = 'Backfills historical cashbook data into the Ledger.'

    def handle(self, *args, **kwargs):
        def get_default_accounts(society_name):
            bank, _ = LedgerAccount.objects.get_or_create(society_name=society_name, name='Bank Account', defaults={'account_type': 'Asset', 'statement_type': 'BalanceSheet'})
            maintenance, _ = LedgerAccount.objects.get_or_create(society_name=society_name, name='Maintenance Income', defaults={'account_type': 'Revenue', 'statement_type': 'PL'})
            expense_acc, _ = LedgerAccount.objects.get_or_create(society_name=society_name, name='General Expenses', defaults={'account_type': 'Expense', 'statement_type': 'PL'})
            return bank, maintenance, expense_acc

        count = 0
        for expense in Expense.objects.all():
            ref_desc = f"New Expense: {expense.payee_name} [REF:EXP-{expense.id}]"
            if not JournalEntry.objects.filter(description=ref_desc).exists():
                bank, _, expense_acc = get_default_accounts(expense.society_name)
                entry = JournalEntry.objects.create(society_name=expense.society_name, description=ref_desc)
                JournalItem.objects.create(entry=entry, account=expense_acc, amount=expense.amount, entry_type='Dr')
                JournalItem.objects.create(entry=entry, account=bank, amount=expense.amount, entry_type='Cr')
                count += 1

        for proof in PaymentProof.objects.filter(status__in=['verified', 'approved']):
            ref_desc = f"Maintenance Receipt [REF:PAY-{proof.id}]"
            if not JournalEntry.objects.filter(description__endswith=ref_desc).exists():
                bank, maintenance, _ = get_default_accounts(proof.society_name)
                amount = proof.extracted_amount if proof.extracted_amount else 0
                if amount > 0:
                    entry = JournalEntry.objects.create(society_name=proof.society_name, description=ref_desc)
                    JournalItem.objects.create(entry=entry, account=bank, amount=amount, entry_type='Dr')
                    JournalItem.objects.create(entry=entry, account=maintenance, amount=amount, entry_type='Cr')
                    count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully backed up {count} historical transactions!'))
