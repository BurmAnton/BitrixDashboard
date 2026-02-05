from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter
from.views import OrganizationViewSet, ContactViewSet

router = DefaultRouter()
router.register(r'organization', OrganizationViewSet, basename='organization')
router.register(r'contact', ContactViewSet, basename='contact')

app_name = 'contact_management'
 
urlpatterns = [
    path('api-guide/', views.api_guide, name="api-guide"),
    path('api/', include(router.urls)),
]