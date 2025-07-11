from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('crm/', include('crm_connector.urls')),
    path('bitrix24/', include('crm_connector.urls')),
    path('education/', include('education_planner.urls')),
] 