from django.urls import path
from . import views

app_name = 'contact_management'
 
urlpatterns = [
    path('import/', views.ContactImport, name='import')
]