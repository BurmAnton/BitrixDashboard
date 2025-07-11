from django.urls import path
from . import views

app_name = 'education_planner'
 
urlpatterns = [
    path('', views.program_list, name='program_list'),
    path('program/create/', views.create_program, name='create_program'),
] 