from django.urls import path
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from django.views.decorators.cache import never_cache
from . import views, api_views

urlpatterns = [
    path('', views.dashboard_redirect, name='home'),
    path('login/', never_cache(auth_views.LoginView.as_view(template_name='core/login.html')), name='login'),
    path('logout/', never_cache(auth_views.LogoutView.as_view(next_page='/login/?logged_out=true')), name='logout'),
    path('register/', views.register, name='register'),
    path('watchman/', views.watchman_dashboard, name='watchman_dashboard'),
    path('maintenance/', views.maintenance_view, name='maintenance'),
    path('gate-records/', views.gate_records, name='gate_records'),
    path('receipt/download/<int:proof_id>/', views.generate_proof_receipt, name='generate_proof_receipt'),
    path('maintenance/delete-proof/<int:proof_id>/', views.delete_payment_proof, name='delete_payment_proof'),
    path('maintenance/verify-proof/<int:proof_id>/<str:action>/', views.verify_payment_proof, name='verify_payment_proof'),
    
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
    path('profile/', views.placeholder_view, {'feature_name': 'Profile'}, name='profile'),
    
    # PWA Service Worker
    path('sw.js', TemplateView.as_view(template_name='core/pwa/sw.js', content_type='application/javascript'), name='sw_js'),
]
