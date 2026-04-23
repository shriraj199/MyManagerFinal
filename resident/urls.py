from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='resident_dashboard'),
    path('bills/', views.bills_list, name='resident_bills'),
    path('complaints/', views.complaints_list, name='resident_complaints'),
    path('more/', views.more_options, name='resident_more'),
    path('receipt/<int:bill_id>/', views.receipt_view, name='receipt_view'),
    path('receipt/<int:bill_id>/pdf/', views.generate_receipt_pdf, name='generate_receipt_pdf'),
    path('receipt/public/<int:bill_id>/<str:signature>/', views.public_generate_receipt_pdf, name='public_generate_receipt_pdf'),

    # ── Owner: Tenant Profiles ──────────────────────────────
    path('rental/', views.rental_management, name='rental_management'),
    path('rental/add-tenant/', views.rental_add_profile, name='rental_add_profile'),
    path('rental/delete-tenant/<int:tenant_id>/', views.rental_tenant_delete, name='rental_tenant_delete'),

    # ── Owner: Rent Charge Settings ─────────────────────────
    path('rental/charge/create/', views.rental_charge_create, name='rental_charge_create'),
    path('rental/charge/edit/<int:rc_id>/', views.rental_charge_edit, name='rental_charge_edit'),
    path('rental/charge/delete/<int:rc_id>/', views.rental_charge_delete, name='rental_charge_delete'),

    # ── Rental Resident: view their rent ────────────────────
    path('my-rent/', views.rental_dashboard, name='rental_dashboard'),
]
