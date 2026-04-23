# Core URL Configuration - Triggering Build
from django.urls import path
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from django.views.decorators.cache import never_cache
from . import views, api_views, accounting_views

urlpatterns = [
    path('', views.dashboard_redirect, name='home'),
    path('login/', never_cache(auth_views.LoginView.as_view(template_name='core/login.html')), name='login'),
    path('logout/', never_cache(auth_views.LogoutView.as_view(next_page='/login/?logged_out=true')), name='logout'),
    path('register/', views.register, name='register'),
    path('watchman/', views.watchman_dashboard, name='watchman_dashboard'),
    path('maintenance/', views.maintenance_view, name='maintenance'),
    path('gate-records/', views.gate_records, name='gate_records'),
    path('receipt/download/<int:proof_id>/', views.generate_proof_receipt, name='generate_proof_receipt'),
    path('maintenance/record-advance/', views.record_advance_payment, name='record_advance_payment'),
    path('maintenance/add-charge/', views.add_manual_charge, name='add_manual_charge'),
    path('maintenance/delete-proof/<int:proof_id>/', views.delete_payment_proof, name='delete_payment_proof'),
    path('maintenance/verify-proof/<int:proof_id>/<str:action>/', views.verify_payment_proof, name='verify_payment_proof'),
    path('maintenance/ocr-preview/', views.process_ocr_preview, name='process_ocr_preview'),
    path('subscription/', views.subscription_view, name='subscription_view'),
    path('members/unpaid-report/', views.download_unpaid_report, name='download_unpaid_report'),
    path('members/toggle-access/<int:user_id>/', views.toggle_subscription_access, name='toggle_subscription_access'),
    path('pro-management/', views.pro_management, name='pro_management'),
    path('force-migrate/', views.force_migrate),
    
    # API Endpoints
    path('api/register/', api_views.register_user, name='api_register'),
    path('api/verify-upi/', api_views.verify_upi, name='api_verify_upi'),
    
    # notices (ACTUAL VIEW)
    path('notices/', views.notices_view, name='notices'),
    path('facilities/', views.placeholder_view, {'feature_name': 'Facilities'}, name='facilities'),
    path('voting/', views.placeholder_view, {'feature_name': 'Voting'}, name='voting'),
    path('members/', views.members_view, name='members'),
    path('vehicles/', views.placeholder_view, {'feature_name': 'Vehicles'}, name='vehicles'),
    path('emergency/', views.placeholder_view, {'feature_name': 'Emergency'}, name='emergency'),
    path('profile/', views.profile_view, name='profile'),
    
    # PWA Service Worker
    path('sw.js', TemplateView.as_view(template_name='core/pwa/sw.js', content_type='application/javascript'), name='sw_js'),
    
    # Accounting Views
    path('accounting/', accounting_views.accounting_dashboard, name='accounting_dashboard'),
    path('accounting/setup-defaults/', accounting_views.setup_default_accounts, name='accounting_setup_defaults'),
    path('accounting/add-entry/', accounting_views.add_journal_entry, name='accounting_add_entry'),
    path('accounting/delete-entry/<int:entry_id>/', accounting_views.delete_journal_entry, name='accounting_delete_entry'),
    path('accounting/trial-balance/', accounting_views.trial_balance, name='accounting_trial_balance'),
    path('accounting/ledger/<int:account_id>/', accounting_views.account_ledger, name='accounting_account_ledger'),
    path('accounting/final-accounts/', accounting_views.final_accounts, name='accounting_final_accounts'),
    path('accounting/full-report/', accounting_views.full_accounting_report, name='accounting_full_report'),
    path('accounting/full-report/download/', accounting_views.download_report_pdf, name='accounting_download_report_pdf'),
]
