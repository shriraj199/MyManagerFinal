from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='company_dashboard'),
    path('generate_code/', views.generate_code, name='generate_code'),
    path('delete_society/<str:society_name>/', views.delete_society, name='delete_society'),
    path('delete_secretary/<int:secretary_id>/', views.delete_secretary, name='delete_secretary'),
]
