from django.urls import path
from . import views
from .views import ObjectHistoryView

app_name = 'crm_connector'

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('pipelines/', views.pipelines_dashboard, name='pipelines_dashboard'),
    path('sync/', views.sync_data, name='sync_data'),
    path('sync-pipelines/', views.sync_pipelines, name='sync_pipelines'),
    path('check-pipelines/', views.check_pipelines, name='check_pipelines'),
    path('import-deals/', views.import_deals_from_excel, name='import_deals'),
    path('crm/import-atlas/', views.import_atlas_applications, name='import_atlas_applications'),
    path('atlas-dashboard/', views.atlas_dashboard, name='atlas_dashboard'),
    path('crm/atlas-dashboard/', views.atlas_dashboard, name='crm_atlas_dashboard'),
    path('history/<str:model>/<int:pk>/', ObjectHistoryView.as_view(), name='object_history'),
    path('import-not-atlas/', views.import_not_atlas, name="import_not_atlas"),
    path('attestation-progress', views.attestation_progress, name="attestation_progress"),
    path('lead-dashboard', views.lead_dashboard, name="lead-dashboard")
]