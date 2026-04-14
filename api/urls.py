from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter
from .views import OrganizationViewSet, ContactViewSet, GetAllViewSet, GetViewSet, ListenerProgressViewSet, EducationProgramViewSet

router = DefaultRouter()
router.register(r'listener-progress', ListenerProgressViewSet, basename='listener-progress')
router.register(r'organization', OrganizationViewSet, basename='organization')
router.register(r'contact', ContactViewSet, basename='contact')
router.register(r'get_all', GetAllViewSet, basename='get_all')
router.register(r'get', GetViewSet, basename='get')
router.register(r'program', EducationProgramViewSet, basename='program')

app_name = 'api'
 
urlpatterns = [
    path('guide/', views.api_guide, name="guide"),
    path('guide/download/', views.api_guide_download_md, name="guide_download_md"),
    path('', include(router.urls))
]