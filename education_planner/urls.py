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
    
    # Маршруты для допсоглашений
    path('agreements/<int:agreement_id>/supplements/create/', views.create_supplement, name='create_supplement'),
    path('supplements/<int:pk>/', views.supplement_detail, name='supplement_detail'),
] 