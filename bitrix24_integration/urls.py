from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('crm/', include('crm_connector.urls')),
    path('bitrix24/', include('crm_connector.urls')),
    path('education/', include('education_planner.urls')),
]

# Добавляем отдачу статических файлов в development режиме
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 