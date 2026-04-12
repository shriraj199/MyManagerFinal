from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from company_panel import views as company_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('resident/', include('resident.urls')),
    path('admin_panel/', include('admin_panel.urls')),
    path('company/', include('company_panel.urls')),
    path('danger/flush/', company_views.dangerous_flush_database),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
