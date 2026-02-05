from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
import django_filters
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from .models import Contact, Organization, Projects

def api_guide(request):
    from django.contrib.auth.models import User
    from rest_framework.authtoken.models import Token
    import requests
    import urllib.parse

    if not request.user.is_authenticated:
        messages.warning(request, 'Для доступа к REST API необходимо войти в систему.')
        return redirect(f'{settings.LOGIN_URL}?next={request.path}')
    
    
    login = User.objects.filter(username=request.user.username).first()
    tkn = Token.objects.filter(user=login).first()
    group = 'organization'
    if 'contact' in request.GET:
        group = 'contact'
    elif 'organization' in request.GET:
        group= 'organization'
    url = f'http://{request.get_host()}/contacts/api/{group}' 

    headers = { 'Authorization': f'Token {tkn}' }

    params = {}
    for arg in request.POST.dict():
        value = request.POST.dict().get(arg)
        if arg != 'csrfmiddlewaretoken' and arg != 'apiLink' and value != '':
            params.setdefault(arg, value)
    
    if request.method == 'POST':
        response = requests.get(url,headers=headers, params=params)
    else:
        response = requests.get(url,headers=headers)
    import json
    try:
        jsn = json.dumps(response.json())
    except Exception as e:
        print(f"Не удалось преобразовать в json: {e}")
        jsn = str(response)
    context={
        'login': login,
        'token': tkn,
        'JsonReponse': jsn,
        'URL': str(urllib.parse.unquote(response.url))
    }

    return render(request, f"contact_management/{group}_api_form.html", context=context)

class ProjectsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Projects
        fields = ["name"]

class OrganizationSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='type.name')
    region = serializers.CharField(source='region.name')
    prof_activity = ProjectsSerializer(many=True, read_only=True)
    fed_district = serializers.CharField(source='region.federalDistrict')
    projects = ProjectsSerializer(many=True, read_only=True)
    class Meta:
        model = Organization
        fields =[
            'name',
            'full_name',
            'type',
            'region',
            'federal_company',
            'fed_district',
            'prof_activity',
            'projects',
            'is_active',
            'created_at',
            'updated_at'
        ]
        
class OrganizationFilter(django_filters.FilterSet):
    type = django_filters.CharFilter(field_name='type__name', lookup_expr='exact')
    date = django_filters.CharFilter(field_name='created_at', lookup_expr='contains')
    
    prof_activity = django_filters.CharFilter(method='filter_prof_activity')
    prof_activity__contains = django_filters.CharFilter(method='filter_prof_activity_contains')

    project = django_filters.CharFilter(field_name='projects__name', lookup_expr='contains')

    region = django_filters.CharFilter(field_name='region__name', lookup_expr='exact')
    region__contains = django_filters.CharFilter(field_name='region__name', lookup_expr='contains')

    fed_district = django_filters.CharFilter(field_name='region__federalDistrict__name', lookup_expr='exact')
    fed_district__contains = django_filters.CharFilter(field_name='region__federalDistrict__name', lookup_expr='contains')

    federal = django_filters.BooleanFilter(field_name='federal_company')

    class Meta:
        model = Organization
        fields = []

    def filter_prof_activity(self, queryset, name, value):
        if not self.data.get("type") or self.data.get("type") != "РОИВ":
            return queryset
        return queryset.filter(prof_activity__name=value)

    def filter_prof_activity_contains(self, queryset, name, value):
        if not self.data.get("type") or self.data.get("type") != "РОИВ":
            return queryset
        return queryset.filter(prof_activity__name__contains=value)

class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    filterset_class = OrganizationFilter
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filter_backends = [DjangoFilterBackend]

class ContactSerializer(serializers.ModelSerializer):
    organization = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = Contact
        fields = [
            "type",
            "comment",
            "current",
            "organization",
            "first_name",
            "last_name",
            "middle_name",
            "position",
            "first_name_dat",
            "last_name_dat",
            "middle_name_dat",
            "position_dat",
            "manager",
            "department_name",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.type == "person":
            # оставляем только персональные поля
            keep = [
                "type",
                "comment",
                "current",
                "organization",
                "first_name",
                "last_name",
                "middle_name",
                "position",
                "first_name_dat",
                "last_name_dat",
                "middle_name_dat",
                "position_dat",
                "manager",
            ]
        elif instance.type == "department":
            # оставляем только поля подразделения
            keep = [
                "type",
                "comment",
                "current",
                "organization",
                "department_name",
            ]
        else:
            keep = ["type", "comment", "current", "organization"]

        return {k: v for k, v in data.items() if k in keep}

class ContactFilter(django_filters.FilterSet):
    organization = django_filters.CharFilter(field_name='organization__name', lookup_expr='exact')
    organization__contains = django_filters.CharFilter(field_name='organization__name', lookup_expr='contains')
    
    type = django_filters.CharFilter(field_name='type', lookup_expr='exact')
    
    deartment = django_filters.CharFilter(method='filter_department')
    deartment__contains = django_filters.CharFilter(method='filter_department_contains')
    
    manager = django_filters.BooleanFilter(method='filter_manager')

    class Meta:
        model = Contact
        fields = [] 
    
    def filter_department(self, queryset, name, value):
        if not self.data.get("type") or self.data.get("type") != "department":
            return queryset
        return queryset.filter(deartment__name=value)

    def filter_department_contains(self, queryset, name, value):
        if not self.data.get("type") or self.data.get("type") != "department":
            return queryset
        return queryset.filter(deartment__name__contains=value)
    
    def filter_manager(self, queryset, name, value):
        if not self.data.get("type") or self.data.get("type") != "person":
            return queryset
        return queryset.filter(manager=value)

class ContactViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    filterset_class = ContactFilter
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    filter_backends = [DjangoFilterBackend]