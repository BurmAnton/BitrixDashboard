from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter
from.views import OrganizationViewSet, ContactViewSet, GetAllViewSet

router = DefaultRouter()
router.register(r'organization', OrganizationViewSet, basename='organization')
router.register(r'contact', ContactViewSet, basename='contact')
router.register(r'get_all', GetAllViewSet, basename='get_all')

app_name = 'contact_management'
 
urlpatterns = [
    path('api-guide/', views.api_guide, name="api-guide"),
    path('api/', include(router.urls)),
]