from django.shortcuts import render
from django.apps import apps

from contact_management.models import (
    CommunicationInteraction,
    Contact,
    ContactEmail,
    ContactPhone,
    FederalDistrict,
    Organization,
    OrganizationType,
    ProfActivity,
    Projects,
    ROIV,
    Region,
)
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
from django.db.models import Q
from django.http import JsonResponse, HttpResponse, Http404

from .guide_markdown import get_guide_doc_path, render_guide_html_for_key

# Create your views here.

def _guide_doc_key(request):
    """Ключ раздела гида (имя шаблона без _api_form.html). Логика совпадает с api_guide."""
    if 'listener-progress' in request.GET:
        return 'listener-progress'
    if 'program' in request.GET:
        return 'program'
    if 'contact' in request.GET:
        return 'contact'
    if 'communication' in request.GET:
        return 'communication'
    if 'organization' in request.GET:
        return 'organization'
    if 'get_all' in request.GET:
        return 'get_all'
    if 'get_call' in request.GET:
        return 'get'
    return 'organization'

_GUIDE_MD_FILENAMES = {
    'organization': 'rest-api-organizations.md',
    'contact': 'rest-api-contacts.md',
    'communication': 'rest-api-communication.md',
    'program': 'rest-api-programs.md',
    'get_all': 'rest-api-get-all.md',
    'get': 'rest-api-get-object.md',
    'listener-progress': 'rest-api-listener-progress.md',
}

def api_guide_download_md(request):
    """Отдаёт документацию текущего раздела гида как скачиваемый .md файл."""
    if not request.user.is_authenticated:
        messages.warning(request, 'Для доступа к REST API необходимо войти в систему.')
        return redirect(f'{settings.LOGIN_URL}?next={request.path}')
    if not request.user.is_staff and not request.user.is_superuser:
        return redirect('/')

    key = _guide_doc_key(request)
    path = get_guide_doc_path(key)
    if not path.is_file():
        raise Http404('Документация в формате Markdown для этого раздела не найдена.')

    content = path.read_text(encoding='utf-8')
    filename = _GUIDE_MD_FILENAMES.get(key, f'{key}.md')
    response = HttpResponse(content, content_type='text/markdown; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

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
    if 'communication' in request.GET:
        group = 'communication'
    elif 'organization' in request.GET:
        group= 'organization'
    elif 'get_all' in request.GET:
        group= 'get_all'
        if 'model' in request.POST.dict():
            group = f"get_all/{request.POST.dict().get('model')}"
    url = f'http://{request.get_host()}/api/{group}'
    guide_url = group
    if 'get_all' in guide_url:
        guide_url = 'get_all'

    headers = { 'Authorization': f'Token {tkn}' }
    api_method = "GET"
    api_action = "list"
    request_body = "{}"
    body_error = None

    params = {}
    for arg in request.POST.dict():
        value = request.POST.dict().get(arg)
        if arg not in ('csrfmiddlewaretoken', 'apiLink', 'model', 'api_method', 'api_action', 'request_body') and value != '':
            params.setdefault(arg, value)
    
    if 'get_call' in request.GET:
        url = f'http://{request.get_host()}/api/get/'
        guide_url = 'get'

    import json
    payload = None
    if request.method == 'POST' and guide_url in ('organization', 'contact', 'communication'):
        api_method = request.POST.get('api_method', 'GET').upper()
        api_action = request.POST.get('api_action', 'list')
        request_body = request.POST.get('request_body', '{}').strip() or '{}'

        if api_action == 'list':
            url = f'http://{request.get_host()}/api/{guide_url}/'
            api_method = 'GET'
        elif api_action == 'add':
            url = f'http://{request.get_host()}/api/{guide_url}/add/'
            api_method = 'POST'
        elif api_action == 'update':
            url = f'http://{request.get_host()}/api/{guide_url}/update/'
            api_method = 'PATCH'

        if api_method in ('POST', 'PATCH'):
            try:
                payload = json.loads(request_body)
                if not isinstance(payload, dict):
                    body_error = 'Тело запроса должно быть JSON-объектом.'
            except json.JSONDecodeError as e:
                body_error = f'Ошибка JSON: {e}'

    if request.method == 'POST':
        if body_error:
            response = None
            jsn = {"error": body_error}
        elif api_method in ('POST', 'PATCH'):
            headers = {**headers, 'Content-Type': 'application/json'}
            response = requests.request(api_method, url, headers=headers, json=payload or {})
        else:
            response = requests.get(url, headers=headers, params=params)
    else:
        response = requests.get(url, headers=headers)

    if not body_error:
        try:
            if response.status_code in (200, 201):
                jsn = json.dumps(response.json(), ensure_ascii=False, indent=2)
            else:
                jsn = {f"HTTP {response.status_code}": response.text[:1000]}
        except Exception as e:
            jsn = f"Ошибка: {e}"

    context={
        'login': login,
        'token': tkn,
        'JsonReponse': jsn,
        'URL': str(urllib.parse.unquote(response.url)) if response else url,
        'ChoiseFields': ChoiseFields,
        'api_method': api_method,
        'api_action': api_action,
        'request_body': request_body,
        'guide_html': render_guide_html_for_key(guide_url),
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
    type = serializers.SerializerMethodField()
    region = serializers.SerializerMethodField()
    prof_activity = serializers.SerializerMethodField()
    fed_district = serializers.SerializerMethodField()
    projects = ProjectsSerializer(many=True, read_only=True)

    def get_type(self, obj):
        return obj.type.name if obj.type_id else None

    def get_region(self, obj):
        return obj.region.name if obj.region_id else None

    def to_representation(self, instance):
        """Всегда возвращаем все поля; prof_activity — массив, не null."""
        data = super().to_representation(instance)
        if data.get('prof_activity') is None:
            data['prof_activity'] = []
        return data

    def get_prof_activity(self, obj):
        try:
            return [pa.name for pa in obj.prof_activity.all()]
        except Exception:
            return []

    def get_fed_district(self, obj):
        if obj.region_id and obj.region.federalDistrict_id:
            return obj.region.federalDistrict.name
        return None
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


def parse_record_history(data):
    """По умолчанию True — записывать историю (django-simple-history)."""
    v = data.get("record_history")
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


class HistoryPagination(Pagination):
    """Только для эндпоинтов /history/, не меняет поведение list()."""
    pass


class HistoricalOrganizationRecordSerializer(serializers.ModelSerializer):
    history_user = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    region = serializers.SerializerMethodField()
    roiv = serializers.SerializerMethodField()
    parent_company = serializers.SerializerMethodField()
    prof_activity = serializers.SerializerMethodField()

    class Meta:
        model = apps.get_model("contact_management", "HistoricalOrganization")
        fields = [
            "history_id",
            "history_date",
            "history_type",
            "history_change_reason",
            "name",
            "full_name",
            "inn",
            "federal_company",
            "is_active",
            "created_at",
            "updated_at",
            "type",
            "region",
            "roiv",
            "parent_company",
            "prof_activity",
            "history_user",
        ]

    def get_history_user(self, obj):
        u = obj.history_user
        if u is None:
            return None
        return {"id": u.pk, "username": getattr(u, "username", str(u.pk))}

    def get_type(self, obj):
        if obj.type_id:
            t = OrganizationType.objects.filter(pk=obj.type_id).first()
            return t.name if t else None
        return None

    def get_region(self, obj):
        if obj.region_id:
            r = Region.objects.filter(pk=obj.region_id).first()
            return r.name if r else None
        return None

    def get_roiv(self, obj):
        if obj.roiv_id:
            r = ROIV.objects.filter(pk=obj.roiv_id).first()
            return r.name if r else None
        return None

    def get_parent_company(self, obj):
        if obj.parent_company_id:
            p = Organization.objects.filter(pk=obj.parent_company_id).first()
            return p.inn if p else None
        return None

    def get_prof_activity(self, obj):
        Through = apps.get_model("contact_management", "HistoricalOrganization_prof_activity")
        rows = Through.objects.filter(history_id=obj.history_id)
        names = []
        for row in rows:
            if row.profactivity_id:
                pa = ProfActivity.objects.filter(pk=row.profactivity_id).first()
                if pa:
                    names.append(pa.name)
        return names


class HistoricalContactRecordSerializer(serializers.ModelSerializer):
    history_user = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()

    class Meta:
        model = apps.get_model("contact_management", "HistoricalContact")
        fields = [
            "history_id",
            "history_date",
            "history_type",
            "history_change_reason",
            "id",
            "type",
            "department_name",
            "first_name",
            "last_name",
            "middle_name",
            "first_name_dat",
            "last_name_dat",
            "middle_name_dat",
            "position",
            "position_dat",
            "manager",
            "comment",
            "current",
            "organization",
            "created_at",
            "updated_at",
            "history_user",
        ]

    def get_history_user(self, obj):
        u = obj.history_user
        if u is None:
            return None
        return {"id": u.pk, "username": getattr(u, "username", str(u.pk))}

    def get_organization(self, obj):
        if obj.organization_id:
            o = Organization.objects.filter(pk=obj.organization_id).first()
            return o.inn if o else None
        return None


class OrganizationViewSet(viewsets.ModelViewSet):
    """Viewset организаций, только чтение списка с учетом фильтров"""
    filterset_class = OrganizationFilter
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filter_backends = [DjangoFilterBackend]

    @action(detail=False, methods=["get"], url_path="history")
    def organization_history(self, request):
        inn = request.query_params.get("inn")
        if not inn:
            return Response(
                {"inn": ["Обязательное поле."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        org = Organization.objects.filter(inn=inn).first()
        if org is None:
            return Response(
                {"detail": "Организация с таким ИНН не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )
        qs = org.history.all().order_by("-history_date")
        paginator = HistoryPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = HistoricalOrganizationRecordSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=["post"], url_path="add")
    def add_organization(self, request):
        serializer = self.get_serializer(data=request.data)
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

        obj = Organization.objects.filter(inn=inn).first()
        if obj is None:
            return Response(
                {"detail": "Организация с таким ИНН не найдена."},
                status=status.HTTP_404_NOT_FOUND
            )

        record_history = parse_record_history(request.data)

        serializer = self.get_serializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        prof_activity_names = request.data.get("prof_activity", None)
        projects = request.data.get("projects", None)
        # Обновляем поля модели
        for attr in request.data:
            if attr in ("projects", "prof_activity", "record_history"):
                continue
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
                except Exception:
                    pass

        def _apply_m2m():
            if prof_activity_names is not None:
                if obj.type and obj.type.name == 'РОИВ':
                    prof_objs = []
                    for name in prof_activity_names:
                        pa = ProfActivity.objects.filter(name=name).first()
                        if pa is not None:
                            prof_objs.append(pa)
                    obj.prof_activity.set(prof_objs)
                else:
                    obj.prof_activity.clear()

            if projects is not None:
                project_objs = []
                for name in projects:
                    project = Projects.objects.filter(name=name).first()
                    if project is not None:
                        project_objs.append(project)
                obj.projects.set(project_objs)

        if record_history:
            obj.save()
            _apply_m2m()
        else:
            obj.skip_history_when_saving = True
            try:
                obj.save()
                _apply_m2m()
            finally:
                if hasattr(obj, "skip_history_when_saving"):
                    del obj.skip_history_when_saving

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

    @action(detail=False, methods=["get"], url_path="history")
    def contact_history(self, request):
        cid = request.query_params.get("id")
        if not cid:
            return Response(
                {"id": ["Обязательное поле."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            return Response(
                {"id": ["Должен быть целым числом."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        contact = Contact.objects.filter(id=cid).first()
        if contact is None:
            return Response(
                {"detail": "Контакт с таким id не найден."},
                status=status.HTTP_404_NOT_FOUND,
            )
        qs = contact.history.all().order_by("-history_date")
        paginator = HistoryPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = HistoricalContactRecordSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=["post"], url_path="add")
    def add_contact(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # вытаскиваем INN из валидированных данных            
        try:
            org = Organization.objects.filter(inn=request.data["organization"]).first()
            if org is None:
                return Response(
                    {"organization": ["Организация с таким ИНН не найдена."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception:
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

    @action(detail=False, methods=["patch"], url_path="update")
    def update_contact(self, request):
        contact_id = request.data.get("id")
        if not contact_id:
            return Response(
                {"id": ["Обязательное поле."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        contact = Contact.objects.filter(id=contact_id).first()
        if contact is None:
            return Response(
                {"detail": "Контакт с таким id не найден."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(contact, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if "organization" in request.data:
            org = Organization.objects.filter(inn=request.data.get("organization")).first()
            if org is None:
                return Response(
                    {"organization": ["Организация с таким ИНН не найдена."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            contact.organization = org

        updatable_fields = [
            "type",
            "department_name",
            "first_name",
            "last_name",
            "middle_name",
            "first_name_dat",
            "last_name_dat",
            "middle_name_dat",
            "position",
            "position_dat",
            "manager",
            "comment",
            "current",
        ]
        for field in updatable_fields:
            if field in serializer.validated_data:
                setattr(contact, field, serializer.validated_data[field])

        record_history = parse_record_history(request.data)
        if record_history:
            contact.save()
        else:
            contact.save_without_historical_record()
        return Response(ContactSerializer(contact).data, status=status.HTTP_200_OK)


class CommunicationInteractionSerializer(serializers.ModelSerializer):
    counterparty_organization = serializers.CharField(source="counterparty_organization.inn", read_only=True)
    counterparty_organization_name = serializers.CharField(source="counterparty_organization.name", read_only=True)
    counterparty_contact = serializers.SerializerMethodField()
    our_organization = serializers.CharField(source="our_organization.inn", read_only=True)
    our_organization_name = serializers.CharField(source="our_organization.name", read_only=True)
    project = serializers.CharField(source="project.name", read_only=True)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)

    class Meta:
        model = CommunicationInteraction
        fields = [
            "id",
            "counterparty_organization",
            "counterparty_organization_name",
            "counterparty_contact",
            "our_organization",
            "our_organization_name",
            "channel",
            "channel_display",
            "occurred_at",
            "result",
            "project",
            "created_at",
            "updated_at",
        ]

    def get_counterparty_contact(self, obj):
        contact = obj.counterparty_contact
        if contact is None:
            return None
        fio = " ".join(filter(None, [contact.last_name, contact.first_name, contact.middle_name])).strip()
        return {
            "id": contact.id,
            "fio": fio or None,
            "position": contact.position,
        }


class CommunicationInteractionPayloadSerializer(serializers.Serializer):
    counterparty_organization = serializers.CharField(required=True)
    counterparty_contact = serializers.IntegerField(required=False, allow_null=True)
    our_organization = serializers.CharField(required=True)
    channel = serializers.ChoiceField(choices=CommunicationInteraction.Channel.choices)
    occurred_at = serializers.DateTimeField()
    result = serializers.CharField()
    project = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class CommunicationInteractionFilter(django_filters.FilterSet):
    organization = django_filters.AllValuesMultipleFilter(field_name="counterparty_organization__inn")
    counterparty_inn = django_filters.AllValuesMultipleFilter(field_name="counterparty_organization__inn")
    contact_id = django_filters.NumberFilter(field_name="counterparty_contact__id")
    our_organization = django_filters.AllValuesMultipleFilter(field_name="our_organization__inn")
    project = django_filters.CharFilter(field_name="project__name", lookup_expr="icontains")
    channel = django_filters.AllValuesMultipleFilter(field_name="channel")
    occurred_after = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_before = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")

    class Meta:
        model = CommunicationInteraction
        fields = []


class CommunicationInteractionViewSet(viewsets.ModelViewSet):
    filterset_class = CommunicationInteractionFilter
    queryset = CommunicationInteraction.objects.select_related(
        "counterparty_organization",
        "counterparty_contact",
        "our_organization",
        "project",
    ).all()
    serializer_class = CommunicationInteractionSerializer
    filter_backends = [DjangoFilterBackend]
    pagination_class = Pagination

    def _validate_payload(self, data, partial=False):
        serializer = CommunicationInteractionPayloadSerializer(data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _resolve_payload(self, data, instance=None):
        attrs = {}

        if "counterparty_organization" in data:
            counterparty_inn = data["counterparty_organization"]
            counterparty_org = Organization.objects.filter(inn=counterparty_inn).first()
            if counterparty_org is None:
                raise serializers.ValidationError(
                    {"counterparty_organization": ["Организация-контрагент с таким ИНН не найдена."]}
                )
            attrs["counterparty_organization"] = counterparty_org

        if "our_organization" in data:
            our_inn = data["our_organization"]
            our_org = Organization.objects.filter(inn=our_inn).first()
            if our_org is None:
                raise serializers.ValidationError(
                    {"our_organization": ["Наша организация с таким ИНН не найдена."]}
                )
            if not our_org.is_our_side:
                raise serializers.ValidationError(
                    {"our_organization": ["Организация должна иметь признак is_our_side=true."]}
                )
            attrs["our_organization"] = our_org

        if "counterparty_contact" in data:
            contact_id = data["counterparty_contact"]
            if contact_id is None:
                attrs["counterparty_contact"] = None
            else:
                contact = Contact.objects.filter(id=contact_id).first()
                if contact is None:
                    raise serializers.ValidationError(
                        {"counterparty_contact": ["Контакт с таким id не найден."]}
                    )
                counterparty_org = attrs.get("counterparty_organization")
                if counterparty_org is None and instance is not None:
                    counterparty_org = attrs.get("counterparty_organization", instance.counterparty_organization)
                if counterparty_org and contact.organization_id != counterparty_org.id:
                    raise serializers.ValidationError(
                        {"counterparty_contact": ["Контакт должен принадлежать counterparty_organization."]}
                    )
                attrs["counterparty_contact"] = contact

        if instance is not None and "counterparty_organization" in attrs and "counterparty_contact" not in data:
            current_contact = instance.counterparty_contact
            if current_contact and current_contact.organization_id != attrs["counterparty_organization"].id:
                raise serializers.ValidationError(
                    {
                        "counterparty_contact": [
                            "Текущий контакт не принадлежит новой организации. Передайте counterparty_contact или null."
                        ]
                    }
                )

        if "project" in data:
            project_name = data["project"]
            if not project_name:
                attrs["project"] = None
            else:
                project = Projects.objects.filter(name=project_name).first()
                if project is None:
                    raise serializers.ValidationError({"project": ["Проект с таким названием не найден."]})
                attrs["project"] = project

        for field in ("channel", "occurred_at", "result"):
            if field in data:
                attrs[field] = data[field]
        return attrs

    def _create_interaction(self, data):
        validated_data = self._validate_payload(data)
        attrs = self._resolve_payload(validated_data)
        interaction = CommunicationInteraction(**attrs)
        interaction.full_clean()
        interaction.save()
        return interaction

    def _partial_update_interaction(self, instance, data):
        validated_data = self._validate_payload(data, partial=True)
        attrs = self._resolve_payload(validated_data, instance=instance)
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        return instance

    def create(self, request, *args, **kwargs):
        interaction = self._create_interaction(request.data)
        return Response(self.get_serializer(interaction).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        interaction = self.get_object()
        interaction = self._partial_update_interaction(interaction, request.data)
        return Response(self.get_serializer(interaction).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="add")
    def add_interaction(self, request):
        return self.create(request)

    @action(detail=False, methods=["patch"], url_path="update")
    def update_interaction(self, request):
        interaction_id = request.data.get("id")
        if not interaction_id:
            return Response({"id": ["Обязательное поле."]}, status=status.HTTP_400_BAD_REQUEST)

        interaction = CommunicationInteraction.objects.filter(id=interaction_id).first()
        if interaction is None:
            return Response(
                {"detail": "Запись коммуникации с таким id не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = request.data.copy()
        if hasattr(payload, "dict"):
            payload = payload.dict()
        payload.pop("id", None)
        interaction = self._partial_update_interaction(interaction, payload)
        return Response(self.get_serializer(interaction).data, status=status.HTTP_200_OK)

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

class ProfActivitySerializer(serializers.ModelSerializer):
    """Сериалайзер для получения списка сфер деятельности"""
    class Meta:
        model = ProfActivity
        fields = ["id", "name"]

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
                    "Сферы деятельности": "/api/get_all/prof_activity/",
                },
            }
        )
    
    @action(detail=False, methods=["get"], url_path="prof_activity")
    def prof_activity_list(self, request):
        activities = ProfActivity.objects.all().order_by("name")
        serializer = ProfActivitySerializer(activities, many=True)
        return Response(serializer.data)
    
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
