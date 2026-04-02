from django.shortcuts import render
from contact_management.models import Organization, OrganizationType, ProfActivity, Projects, FederalDistrict, Region, ROIV,  HistoryOrganization, ContactEmail, ContactPhone, Contact
from crm_connector.models import AtlasApplication
from education_planner.models import EducationProgram, ProgramTopics, ProgramSection
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
import django_filters
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework import viewsets
from rest_framework import status
from django_filters.rest_framework import DjangoFilterBackend
from datetime import datetime
from django.db.models import Q
from django.http import JsonResponse

# Create your views here.

def api_guide(request):
    from django.contrib.auth.models import User
    from rest_framework.authtoken.models import Token
    import requests
    import urllib.parse

    if not request.user.is_authenticated:
        messages.warning(request, 'Для доступа к REST API необходимо войти в систему.')
        return redirect(f'{settings.LOGIN_URL}?next={request.path}')
    if not request.user.is_staff and not request.user.is_superuser:
        return redirect('/')
    
    ChoiseFields = {}

    types = OrganizationType.objects.all()
    ChoiseFields.setdefault('type', [obj.name for obj in types])

    prof_activity = ProfActivity.objects.all()
    ChoiseFields.setdefault('prof_activity', [obj.name for obj in prof_activity])

    project = Projects.objects.all()
    ChoiseFields.setdefault('project', [obj.name for obj in project])

    region = Region.objects.all()
    ChoiseFields.setdefault('region', [obj.name for obj in region])

    fed_district = FederalDistrict.objects.all()
    ChoiseFields.setdefault('fed_district', [obj.name for obj in fed_district])

    organization = Organization.objects.all()
    ChoiseFields.setdefault('organization', [obj.inn for obj in organization])
    
    programs = EducationProgram.objects.all()
    ChoiseFields.setdefault('programs', [obj.name for obj in programs])

    login = User.objects.filter(username=request.user.username).first()
    tkn = Token.objects.filter(user=login).first()
    group = 'organization'
    if 'listener-progress' in request.GET:
        group = 'listener-progress'
    if 'program' in request.GET:
        group = 'program'
    if 'contact' in request.GET:
        group = 'contact'
    elif 'organization' in request.GET:
        group= 'organization'
    elif 'get_all' in request.GET:
        group= 'get_all'
        if 'model' in request.POST.dict():
            group = f'get_all/{request.POST.dict().get('model')}'
    url = f'http://{request.get_host()}/api/{group}'
    guide_url = group
    if 'get_all' in guide_url:
        guide_url = 'get_all'

    headers = { 'Authorization': f'Token {tkn}' }

    params = {}
    for arg in request.POST.dict():
        value = request.POST.dict().get(arg)
        if arg != 'csrfmiddlewaretoken' and arg != 'apiLink' and value != '' and arg != 'model':
            params.setdefault(arg, value)
    
    if 'get_call' in request.GET:
        url = f'http://{request.get_host()}/api/get/'
        guide_url = 'get'

    if request.method == 'POST':
        response = requests.get(url,headers=headers, params=params)
    else:
        response = requests.get(url,headers=headers)
    import json
    try:
        if response.status_code == 200:
            jsn = json.dumps(response.json(), ensure_ascii=False, indent=2)
        else:
            jsn = {f"HTTP {response.status_code}": response.text[:1000]}
    except Exception as e:
        jsn = f"Ошибка: {e}"
    context={
        'login': login,
        'token': tkn,
        'JsonReponse': jsn,
        'URL': str(urllib.parse.unquote(response.url)),
        'ChoiseFields': ChoiseFields
    }
    return render(request, f"{guide_url}_api_form.html", context=context)

class ViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

class Pagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"

class ListenerProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = AtlasApplication
        fields = ['application_id', 'full_name', 'potok', 'program', 'JSON_ed_progress']

class ListenerProgressFilter(django_filters.FilterSet):
    application_id = django_filters.CharFilter(field_name='application_id', lookup_expr='exact')
    application_id__contains = django_filters.CharFilter(field_name='application_id', lookup_expr='contains')
    
    full_name = django_filters.CharFilter(field_name='full_name', lookup_expr='exact')
    full_name__contains = django_filters.CharFilter(field_name='full_name', lookup_expr='contains')
    
    potok = django_filters.CharFilter(field_name='potok', lookup_expr='exact')
    potok__contains = django_filters.CharFilter(field_name='potok', lookup_expr='contains')
    
    program = django_filters.CharFilter(field_name='program', lookup_expr='exact')
    program__contains = django_filters.CharFilter(field_name='program', lookup_expr='contains')

    class Meta:
        model = AtlasApplication
        fields = [] 

class ListenerProgressViewSet(ViewSet):
    filterset_class = ListenerProgressFilter
    queryset = AtlasApplication.objects.all()
    serializer_class = ListenerProgressSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['application_id', 'potok', 'program']
    pagination_class = Pagination

class ProjectsSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения списка проектов"""
    class Meta:
        model = Projects
        fields = ["name"]

class ProfActivitySerializer(serializers.ModelSerializer):
    """Сериалайзер для получения списка сфер деятельности"""
    class Meta:
        model = ProfActivity
        fields = ["name"]

class OrganizationSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения списка организаций"""
    type = serializers.CharField(source='type.name', read_only=True)
    region = serializers.CharField(source='region.name', read_only=True)
    prof_activity = ProfActivitySerializer(many=True, read_only=True)
    fed_district = serializers.CharField(source='region.federalDistrict', read_only=True)
    projects = ProjectsSerializer(many=True, read_only=True)
    class Meta:
        model = Organization
        fields =[
            'inn',
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
    """Фильтры API списков организаций"""
    type = django_filters.AllValuesMultipleFilter(field_name='type__name')
    date = django_filters.CharFilter(field_name='created_at', lookup_expr='contains')
    
    prof_activity = django_filters.CharFilter(method='filter_prof_activity_multiple')

    project = django_filters.CharFilter(field_name='projects__name', lookup_expr='contains')

    region = django_filters.AllValuesMultipleFilter(field_name='region__name')

    fed_district = django_filters.AllValuesMultipleFilter(field_name='region__federalDistrict__name')

    federal = django_filters.BooleanFilter(field_name='federal_company')

    class Meta:
        model = Organization
        fields = []

    def filter_prof_activity_multiple(self, queryset, name, value):
            if self.data.get("type") != "РОИВ":
                return queryset
            values = value.split(',') if isinstance(value, str) else value
            q_objects = Q()
            for val in values:
                q_objects |= Q(prof_activity__name__icontains=val)
            return queryset.filter(q_objects).distinct()

class OrganizationViewSet(viewsets.ModelViewSet):
    """Viewset организаций, только чтение списка с учетом фильтров"""
    filterset_class = OrganizationFilter
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filter_backends = [DjangoFilterBackend]

    @action(detail=False, methods=["post"], url_path="add")
    def add_organization(self, request):
        serializer = self.get_serializer(data=request.data)
        print(serializer.is_valid())
        print(serializer.errors)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        projects = request.data.get("projects", [])
        prof_activity_names = request.data.get("prof_activity", [])
        # создаём контакт с найденной организацией
        obj = Organization.objects.create(
            inn=serializer.validated_data["inn"],
            name=serializer.validated_data.get("name", ""),
            full_name=serializer.validated_data.get("full_name", ""),
            type=OrganizationType.objects.filter(name=request.data.get("type", "")).first() or None,
            roiv=ROIV.objects.filter(name=request.data.get("roiv", "")).first() or None,
            region= Region.objects.filter(name=request.data.get("region", "")).first() or None,
            federal_company= serializer.validated_data.get("federal_company", False),
            is_active= serializer.validated_data.get("is_active", True),
            parent_company= Organization.objects.filter(inn=request.data.get("parent_company", "")).first() or None,
        )

        if projects is not None: 
            for name in projects:
                project = Projects.objects.filter(name=name).first()
                if project is not None:
                    obj.projects.add(project)
        if obj.type:
            if prof_activity_names is not None and obj.type.name == 'РОИВ':
                for name in prof_activity_names:
                    prof_activity = ProfActivity.objects.filter(name=name).first()
                    if prof_activity is not None:
                        obj.prof_activity.add(prof_activity)

        return Response(OrganizationSerializer(obj).data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=["patch"], url_path="update")
    def update_organization(self, request):
        inn = request.data.get("inn")
        if not inn:
            return Response(
                {"inn": ["Обязательное поле."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            obj = Organization.objects.filter(inn=inn).first()
        except Organization.DoesNotExist:
            return Response(
                {"detail": "Организация с таким ИНН не найдена."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        HistoryOrganization.objects.create(
            organization=obj,
            name=obj.name,
            status='active',
            date=datetime.now()
        )

        serializer = self.get_serializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        prof_activity_names = request.data.get("prof_activity", None)
        projects = request.data.get("projects", None)
        # Обновляем поля модели
        for attr in request.data:
            if attr == "type":
                setattr(obj, attr, OrganizationType.objects.filter(name=request.data.get(attr, None)).first())
            elif attr == "roiv":
                setattr(obj, attr, ROIV.objects.filter(name=request.data.get(attr, None)).first())
            elif attr == "region":
                setattr(obj, attr, Region.objects.filter(name=request.data.get(attr, None)).first())
            elif attr == "parent_company":
                setattr(obj, attr, Organization.objects.filter(inn=request.data.get(attr, None)).first())
            else:
                try:
                    setattr(obj, attr, request.data.get(attr, None))
                except:
                    pass
        obj.save()
        # Обновляем ManyToMany prof_activity
        if obj.type:
            if prof_activity_names is not None and obj.type.name == 'РОИВ':
                for name in prof_activity_names:
                    prof_activity = ProfActivity.objects.filter(name=name).first()
                    if prof_activity is not None:
                        obj.prof_activity.add(prof_activity)

        # Обновляем ManyToMany projects
        if projects is not None: 
            for name in projects:
                project = Projects.objects.filter(name=name).first()
                if project is not None:
                    obj.projects.add(project)

        return Response(OrganizationSerializer(obj).data, status=status.HTTP_200_OK)

class ContactSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения списка контактов """
    organization = serializers.CharField(source="organization.inn", read_only=True)

    class Meta:
        model = Contact
        fields = "__all__"
        # поля, которые можно указывать при создании/обновлении
        extra_kwargs = {
            "organization": {"required": True},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.type == "person":
            keep = [
                "id",
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
            keep = [
                "id",
                "type",
                "comment",
                "current",
                "organization",
                "department_name",
            ]
        else:
            keep = ["id", "type", "comment", "current", "organization"]

        return {k: v for k, v in data.items() if k in keep}

class ContactFilter(django_filters.FilterSet):
    """Фильтры API списков контактов"""
    organization = django_filters.AllValuesMultipleFilter(field_name='organization__inn')
    
    type = django_filters.AllValuesMultipleFilter(field_name='type')
    
    department = django_filters.CharFilter(method='filter_department_multiple')
    
    manager = django_filters.BooleanFilter(method='filter_manager')

    class Meta:
        model = Contact
        fields = [] 

    def filter_department_multiple(self, queryset, name, value):
        if 'department' not in self.data or self.data.get("type") != "department":
            return queryset
        values = value.split(',') if isinstance(value, str) else value
        q_objects = Q()
        for val in values:
            q_objects |= Q(department_name__icontains=val)
        return queryset.filter(q_objects).distinct()

    def filter_department_contains(self, queryset, name, value):
        if not self.data.get("type") or self.data.get("type") != "department":
            return queryset
        return queryset.filter(department_name__icontains=value)
    
    def filter_manager(self, queryset, name, value):
        if not self.data.get("type") or self.data.get("type") != "person":
            return queryset
        return queryset.filter(manager=value)

class ContactViewSet(viewsets.ModelViewSet):
    """Viewset контактов, только чтение списка с учетом фильтров"""
    filterset_class = ContactFilter
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    filter_backends = [DjangoFilterBackend]

    @action(detail=False, methods=["post"], url_path="add")
    def add_contact(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # вытаскиваем INN из валидированных данных            
        try:
            org = Organization.objects.filter(inn=request.data["organization"]).first()
        except Exception as e:
            return Response(
                {"error": f"Не удалось найти огранизацию контакта"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # создаём контакт с найденной организацией
        contact = Contact.objects.create(
            organization=org,
            type=serializer.validated_data["type"],
            department_name=serializer.validated_data.get("department_name", ""),
            first_name=serializer.validated_data.get("first_name", ""),
            last_name=serializer.validated_data.get("last_name", ""),
            middle_name=serializer.validated_data.get("middle_name", ""),
            first_name_dat=serializer.validated_data.get("first_name_dat", ""),
            last_name_dat=serializer.validated_data.get("last_name_dat", ""),
            middle_name_dat=serializer.validated_data.get("middle_name_dat", ""),
            position=serializer.validated_data.get("position", ""),
            position_dat=serializer.validated_data.get("position_dat", ""),
            manager=serializer.validated_data.get("manager", False),
            comment=serializer.validated_data.get("comment", ""),
            current=serializer.validated_data.get("current", True),
        )

        return Response(ContactSerializer(contact).data, status=status.HTTP_201_CREATED)

class RegionNameSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения списка регионов"""
    class Meta:
        model = Region
        fields = ["name", "code", "is_active"]

class FederalDistrictWithRegionsSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения списка федеральный округов"""
    region = RegionNameSerializer(many=True, read_only=True)
    class Meta:
        model = FederalDistrict
        fields = ["name", "region"]

class OrganizationTypeSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения списка типов организаций"""
    class Meta:
        model = OrganizationType
        fields = "__all__"

class GetAllViewSet(ViewSet):
    """Вьюсет для определния, списки каких моделей вывести"""
    def list(self, request):
        return Response(
            {
                "message": "Выберите конкретный эндпоинт:",
                "endpoints": {
                    "Регионы": "/api/get_all/region/",
                    "Типы организаций": "/api/get_all/organization_type/",
                    "Федеральные округа": "/api/get_all/fed_district/",
                    "Программы": "/api/get_all/program/",
                },
            }
        )
    
    @action(detail=False, methods=["get"], url_path="region")
    def regions(self, request):
        regions = Region.objects.all()
        serializer = RegionNameSerializer(regions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="organization_type")
    def organization_types(self, request):
        org_types = OrganizationType.objects.all()
        serializer = OrganizationTypeSerializer(org_types, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=["get"], url_path="fed_district")
    def federal_districts(self, request):
        districts = FederalDistrict.objects.all()
        serializer = FederalDistrictWithRegionsSerializer(districts, many=True)
        return Response(serializer.data)

class SingleOrganizationSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения списка организаций"""
    type = serializers.CharField(source='type.name', read_only=True)
    region = serializers.CharField(source='region.name', read_only=True)
    prof_activity = serializers.CharField(source='prof_activity.name', read_only=True)
    fed_district = serializers.CharField(source='region.federalDistrict', read_only=True)
    projects = ProjectsSerializer(many=True, read_only=True)
    class Meta:
        model = Organization
        fields =[
            'inn',
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

class TopicSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения объекта программы"""
    class Meta:
        model = ProgramTopics
        fields =[
            'order',
            'name',
            'lecture_hours',
            'practice_hours',
            'selfstudy_hours',
            'consultation_hours',
            'dot_hours',
            'workload',
            'attestation_form',
            'description'
        ]

class SectionSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения объекта программы"""
    topics = TopicSerializer(many=True, read_only = True)
    class Meta:
        model = ProgramSection
        fields = [
            'order',
            'name',
            'lecture_hours',
            'practice_hours',
            'selfstudy_hours',
            'consultation_hours',
            'dot_hours',
            'workload',
            'attestation_form',
            'description',
            'topics'
        ]

class SingleProgramSerializer(serializers.ModelSerializer):
    """Сериалайзер для получения объекта программы"""
    sections = SectionSerializer(many=True, read_only = True)
    class Meta:
        model = EducationProgram
        fields = [
            "name",
            "academic_hours",
            "program_type",
            "study_form",
            "DOT",
            "description",
            "duration",
            "final_attestation",
            "activities",
            "sections"
        ]

class GetViewSet(ViewSet):
    """Вьюсет для GET запросов организаций"""
    filter_backends = [DjangoFilterBackend]

    def list(self, request):
        return Response({
            "message": "Получить объект по уникальному ключу:",
            "endpoint": {
                'Организации': "/api/get/organization/?inn=<ИНН>",
                'Программы': "/api/get/program/?pk=<ИНН>",
            }
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="organization")
    def organization(self, request):
        inn = request.query_params.get('inn')        
        if not inn:
            return Response({
                "error": "ИНН обязателен",
                "usage": "/api/get/organization/?inn=<ИНН>"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.get(inn=inn)
            serializer = SingleOrganizationSerializer(org)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Organization.DoesNotExist:
            return Response({
                "error": f"Организация с ИНН {inn} не найдена"
            }, status=status.HTTP_404_NOT_FOUND)
        
    @action(detail=False, methods=["get"], url_path="program")
    def program(self, request):
        pk = request.query_params.get('pk')        
        if not pk:
            return Response({
                "error": "Ключ обязателен",
                "usage": "/api/get/program/<pk>"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            prog = EducationProgram.objects.get(pk=pk)
            serializer = SingleProgramSerializer(prog)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except EducationProgram.DoesNotExist:
            return Response({
                "error": f"Программа по ключу {pk} не найдена"
            }, status=status.HTTP_404_NOT_FOUND)

class ProgramViewSet(viewsets.ViewSet):
    filterset_class = ListenerProgressFilter
    queryset = AtlasApplication.objects.all()
    serializer_class = ListenerProgressSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['application_id', 'potok', 'program']
    pagination_class = Pagination

class EducationProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = EducationProgram
        fields = '__all__'

class EducationProgramFilter(django_filters.FilterSet):
    """Фильтры API списков программ"""
    name = django_filters.CharFilter(field_name='name', lookup_expr='contains')
    program_type = django_filters.CharFilter(field_name='program_type', lookup_expr='exact')
    study_form = django_filters.CharFilter(field_name='study_form', lookup_expr='exact')
    DOT = django_filters.BooleanFilter(field_name='DOT')
    
    class Meta:
        model = EducationProgram
        fields = []

    def filter_prof_activity_multiple(self, queryset, name, value):
            if self.data.get("type") != "РОИВ":
                return queryset
            values = value.split(',') if isinstance(value, str) else value
            q_objects = Q()
            for val in values:
                q_objects |= Q(prof_activity__name__icontains=val)
            return queryset.filter(q_objects).distinct()

class EducationProgramViewSet(ViewSet):
    filterset_class = EducationProgramFilter
    queryset = EducationProgram.objects.all()
    serializer_class = EducationProgramSerializer
    filter_backends = [DjangoFilterBackend]
