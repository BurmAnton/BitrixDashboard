from django.urls import path
from . import views

app_name = 'education_planner'
 
urlpatterns = [
    path('', views.program_list, name='program_list'),
    path('program/create/', views.create_program, name='create_program'),
    
    # Маршруты для управления договорами
    path('agreements/', views.agreements_dashboard, name='agreements_dashboard'),
    path('agreements/<int:pk>/', views.agreement_detail, name='agreement_detail'),
    path('agreements/create/', views.create_agreement, name='create_agreement'),
    path('agreements/<int:pk>/delete/', views.delete_agreement, name='delete_agreement'),
    
    # Маршруты для управления квотами
    path('agreements/<int:agreement_id>/quotas/', views.manage_quota, name='manage_quota'),
    path('quotas/<int:quota_id>/detail/', views.quota_detail, name='quota_detail'),
    
    # Маршруты для импорта квот
    path('quotas/analyze/', views.analyze_quotas_excel, name='analyze_quotas_excel'),
    path('quotas/regions/save/', views.save_region_mappings, name='save_region_mappings'),
    path('quotas/import/', views.import_quotas_excel, name='import_quotas_excel'),
    path('quotas/template/', views.download_quota_template, name='download_quota_template'),
    
    # Маршруты для допсоглашений
    path('agreements/<int:agreement_id>/supplements/create/', views.create_supplement, name='create_supplement'),
    path('supplements/<int:pk>/', views.supplement_detail, name='supplement_detail'),
] 