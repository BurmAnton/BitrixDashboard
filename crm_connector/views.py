from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect, JsonResponse, Http404
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

import openpyxl
from .tasks import sync_leads, sync_deals, sync_contacts, sync_pipelines_task
from .bitrix24_api import Bitrix24API
from django.views.decorators.csrf import csrf_protect
from .models import Lead, Deal, Contact, Pipeline, Stage, AtlasApplication, StageRule
from django.db.models import Count, Sum, F, ExpressionWrapper, Avg, DurationField
from .models import Lead, Deal, Contact, Pipeline, Stage, AtlasApplication, StageRule, Company
from django.db.models import Count, Sum, F, ExpressionWrapper, Avg, DurationField, Q
from django.contrib import messages
import logging
import pandas as pd
from .forms import ExcelImportForm, AtlasLeadImportForm, LeadImportForm
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# OAuth функции удалены - проект использует webhook-аутентификацию через переменные окружения

def index(request):
    return HttpResponseRedirect(reverse('crm_connector:atlas_dashboard'))

def dashboard(request):
    """Представление для дашборда с данными из Битрикс24"""
    leads_count = Lead.objects.count()
    deals_count = Deal.objects.count()
    contacts_count = Contact.objects.count()
    
    # Суммы по сделкам
    total_amount = Deal.objects.filter(amount__isnull=False).aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    # Статистика по стадиям сделок
    stages = Deal.objects.values('stage').annotate(
        count=Count('id'),
        sum=Sum('amount')
    )
    
    context = {
        'leads_count': leads_count,
        'deals_count': deals_count,
        'contacts_count': contacts_count,
        'total_amount': total_amount,
        'stages': stages,
    }
    
    return render(request, 'crm_connector/dashboard.html', context)

def sync_data(request):
    """API для запуска синхронизации данных"""
    sync_leads.delay()
    sync_deals.delay()
    sync_contacts.delay()
    
    return JsonResponse({'status': 'success', 'message': 'Синхронизация запущена'})

def sync_pipelines(request):
    """Представление для запуска синхронизации воронок и сделок"""
    # Проверяем, аутентифицирован ли пользователь
    if not request.user.is_authenticated:
        messages.warning(request, 'Для синхронизации данных необходимо войти в систему.')
        return redirect(f'{settings.LOGIN_URL}?next={request.path}?year={request.GET.get("year", "all")}')
    
    try:
        # Пытаемся запустить асинхронную синхронизацию через Celery
        try:
            sync_pipelines_task.delay()
            sync_deals.delay()
            messages.success(request, 'Синхронизация воронок и сделок успешно запущена. Обновление данных может занять некоторое время.')
        except Exception as celery_error:
            logger.warning(f"Ошибка Celery: {celery_error}. Запускаем синхронную синхронизацию.")
            
            # Если Celery недоступен, выполняем синхронизацию прямо в запросе
            api = Bitrix24API()
            
            # Синхронизация воронок
            pipelines_result = sync_pipelines_directly(api)
            
            # Синхронизация сделок (основные данные)
            deals_result = sync_deals_directly(api)
            
            messages.success(request, f'Синхронизация выполнена напрямую: {pipelines_result} воронок и {deals_result} сделок.')
        
        # Редирект на страницу с воронками с сохранением выбранного года
        selected_year = request.GET.get('year', 'all')
        return redirect(f'/crm/pipelines/?year={selected_year}')
    
    except Exception as e:
        messages.error(request, f'Ошибка при синхронизации: {str(e)}')
        return redirect('crm_connector:pipelines_dashboard')

def sync_pipelines_directly(api):
    """Синхронная версия функции для синхронизации воронок"""
    try:
        # Получаем данные о воронках
        pipelines_data = api.get_all('crm.pipeline.list')
        pipelines_count = 0
        stages_count = 0
        
        for pipeline_data in pipelines_data:
            pipeline_id = pipeline_data.get('ID')
            
            # Создаем или обновляем воронку
            pipeline, created = Pipeline.objects.update_or_create(
                bitrix_id=pipeline_id,
                defaults={
                    'name': pipeline_data.get('NAME', ''),
                    'sort': int(pipeline_data.get('SORT', 0)),
                    'is_main': pipeline_data.get('IS_MAIN', 'N') == 'Y',
                    'last_sync': timezone.now(),
                    'is_active': True
                }
            )
            pipelines_count += 1
            
            # Получаем этапы для этой воронки
            stages_data = api.get_all('crm.status.list', {
                'filter': {'ENTITY_ID': f'DEAL_STAGE_{pipeline_id}'}
            })
            
            for stage_data in stages_data:
                stage_id = stage_data.get('STATUS_ID')
                
                # Определяем тип этапа
                name = stage_data.get('NAME', '')
                semantic_info = stage_data.get('SEMANTICS', '')
                
                # По умолчанию этап в процессе
                stage_type = 'process'
                
                # Определяем тип этапа по семантике или имени
                if semantic_info == 'S':
                    stage_type = 'success'
                elif semantic_info == 'F':
                    stage_type = 'failure'
                
                # Создаем или обновляем этап
                Stage.objects.update_or_create(
                    bitrix_id=stage_id,
                    defaults={
                        'pipeline': pipeline,
                        'name': name,
                        'sort': int(stage_data.get('SORT', 0)),
                        'type': stage_type,
                        'color': stage_data.get('COLOR', '')
                    }
                )
                stages_count += 1
        
        return f"{pipelines_count} воронок и {stages_count} этапов"
    
    except Exception as e:
        logger.error(f"Ошибка при синхронизации воронок напрямую: {str(e)}")
        return f"Ошибка: {str(e)}"

def sync_deals_directly(api):
    """Синхронная версия функции для синхронизации сделок"""
    try:
        # Получаем сделки из API
        deals = api.get_all_deals()
        current_time = timezone.now()
        synced_count = 0
        
        # Получаем все воронки и этапы для быстрого доступа
        pipelines = {p.bitrix_id: p for p in Pipeline.objects.all()}
        stages = {s.bitrix_id: s for s in Stage.objects.all()}
        
        for deal_data in deals:
            try:
                # Обработка сделки
                pipeline_id = str(deal_data.get('CATEGORY_ID', '0'))
                stage_id = deal_data.get('STAGE_ID', '')
                
                pipeline = pipelines.get(pipeline_id)
                stage = stages.get(stage_id)
                
                # Создаем или обновляем сделку
                Deal.objects.update_or_create(
                    bitrix_id=deal_data['ID'],
                    defaults={
                        'title': deal_data['TITLE'],
                        'pipeline': pipeline,
                        'stage': stage,
                        'amount': float(deal_data.get('OPPORTUNITY', 0) or 0),
                        'last_sync': current_time,
                        'details': deal_data
                    }
                )
                synced_count += 1
            except Exception as deal_error:
                logger.error(f"Ошибка при обработке сделки {deal_data.get('ID')}: {str(deal_error)}")
        
        return synced_count
    
    except Exception as e:
        logger.error(f"Ошибка при синхронизации сделок напрямую: {str(e)}")
        return f"Ошибка: {str(e)}"

def check_pipelines(request):
    """Проверка необходимости синхронизации данных"""
    # Получаем время последней синхронизации
    last_sync = None
    if Deal.objects.exists():
        last_sync = Deal.objects.order_by('-last_sync').first().last_sync
    
    # Если нет данных о синхронизации или прошло больше 1 часа
    if not last_sync or (timezone.now() - last_sync).total_seconds() > 3600:
        try:
            # Сначала пробуем Celery
            sync_pipelines_task.delay()
            sync_deals.delay()
            return JsonResponse({'sync_triggered': True, 'method': 'celery'})
        except Exception as celery_error:
            logger.warning(f"Ошибка Celery: {celery_error}. Запускаем синхронную синхронизацию.")
            
            # Если Celery недоступен, выполняем синхронизацию напрямую
            api = Bitrix24API()
            sync_pipelines_directly(api)
            sync_deals_directly(api)
            return JsonResponse({'sync_triggered': True, 'method': 'direct'})
    
    return JsonResponse({'sync_triggered': False})

def pipelines_dashboard(request):
    """Представление для дашборда с воронками продаж"""
    try:
        # Получаем выбранный год из параметров запроса
        selected_year = request.GET.get('year', 'all')
        
        # Проверяем наличие данных
        pipeline_count = Pipeline.objects.count()
        if pipeline_count == 0:
            # Если нет данных о воронках, запускаем синхронизацию
            api = Bitrix24API()
            api.sync_pipelines_and_stages()
            return redirect('crm_connector:pipelines_dashboard')
        
        deals_count = Deal.objects.count()
        if deals_count == 0:
            # Если нет данных о сделках, показываем сообщение
            context = {
                'error': 'Нет данных о сделках. Запустите синхронизацию.',
                'empty_deals': True
            }
            return render(request, 'crm_connector/error.html', context)
        
        # Получаем все доступные года из сделок
        available_years = Deal.objects.dates('created_at', 'year').values_list('created_at__year', flat=True)
        available_years = sorted(list(set(available_years)), reverse=True)
        
        # Получаем все воронки
        pipelines = Pipeline.objects.filter(is_active=True).order_by('-is_main', 'sort')
        
        dashboard_data = []
        
        for pipeline in pipelines:
            # Получаем все этапы воронки
            stages = Stage.objects.filter(pipeline=pipeline).order_by('sort')
            
            # Базовый фильтр для сделок - по воронке
            deals_filter = {'pipeline': pipeline}
            
            # Добавляем фильтр по году, если выбран конкретный год
            if selected_year != 'all' and selected_year.isdigit():
                year = int(selected_year)
                deals_filter['created_at__year'] = year
            
            # Группируем этапы по типам для прогресс-бара
            stage_types_data = {
                'process': {'count': 0, 'color': '#5bc0de', 'name': 'В процессе', 'amount': 0},
                'success': {'count': 0, 'color': '#5cb85c', 'name': 'Успешно завершенные', 'amount': 0},
                'failure': {'count': 0, 'color': '#d9534f', 'name': 'Неуспешно завершенные', 'amount': 0}
            }
            
            # Сначала считаем общее количество сделок по всем этапам с учетом фильтра по году
            total_deals = 0
            for stage in stages:
                stage_filter = deals_filter.copy()
                stage_filter['stage'] = stage
                deals_on_stage = Deal.objects.filter(**stage_filter)
                deals_count = deals_on_stage.count()
                total_deals += deals_count
                
                # Группируем сделки по типам этапов и суммируем суммы
                stage_amount = deals_on_stage.aggregate(total=Sum('amount'))['total'] or 0
                stage_types_data[stage.type]['count'] += deals_count
                stage_types_data[stage.type]['amount'] += stage_amount
            
            # Рассчитываем проценты для типов этапов
            stage_types_list = []
            if total_deals > 0:
                # Сначала вычисляем все проценты
                for type_key, type_data in stage_types_data.items():
                    # Сохраняем значение как число для вычислений
                    percent_num = round(type_data['count'] / total_deals * 100, 1)
                    type_data['percent'] = percent_num
                    # Добавляем отдельное строковое значение для CSS
                    type_data['percent_css'] = str(percent_num).replace(',', '.')
                    stage_types_list.append({'type': type_key, **type_data})
                
                # Подсчет суммы процентов - теперь работает с числами
                total_percent = sum(item['percent'] for item in stage_types_list)
                
                # Если сумма не равна 100%, корректируем
                if total_percent != 100.0:
                    # Находим элемент с наибольшим значением для корректировки
                    max_item = max(stage_types_list, key=lambda x: x['count'])
                    # Добавляем или убавляем разницу
                    max_item['percent'] += (100.0 - total_percent)
            else:
                # Равномерно распределяем 100% между всеми типами
                type_keys = list(stage_types_data.keys())
                equal_percent = 100.0 / len(type_keys)
                
                for i, type_key in enumerate(type_keys):
                    # Последнему типу отдаем остаток, чтобы избежать ошибок округления
                    if i == len(type_keys) - 1:
                        current_percent = 100.0 - (equal_percent * (len(type_keys) - 1))
                    else:
                        current_percent = equal_percent
                    
                    stage_types_data[type_key]['percent'] = current_percent
                    stage_types_data[type_key]['percent_css'] = str(current_percent).replace(',', '.')
                    stage_types_list.append({'type': type_key, **stage_types_data[type_key]})
            
            # Сортируем типы для прогресс-бара: сначала в процессе, потом успешные, потом неуспешные
            stage_types_list.sort(key=lambda x: {'process': 0, 'success': 1, 'failure': 2}.get(x['type'], 3))
            
            # Теперь создаем данные по этапам с корректными процентами (для таблицы)
            stages_data = []
            total_amount = 0
            total_open_deals = 0
            total_closed_deals = 0
            total_success_amount = 0
            
            for stage in stages:
                # Все сделки на этапе с учетом фильтра по году
                stage_filter = deals_filter.copy()
                stage_filter['stage'] = stage
                total_deals_on_stage = Deal.objects.filter(**stage_filter)
                
                # Количество всех сделок на этапе
                deals_count = total_deals_on_stage.count()
                
                # Количество открытых и закрытых сделок на этапе
                open_deals = total_deals_on_stage.filter(is_closed=False).count()
                closed_deals = total_deals_on_stage.filter(is_closed=True).count()
                
                # Сумма по сделкам на этапе
                deals_amount = total_deals_on_stage.aggregate(total=Sum('amount'))['total'] or 0
                
                # Сумма по успешно завершенным сделкам (только для этапов типа 'success')
                success_amount = 0
                if stage.type == 'success':
                    success_amount = deals_amount
                
                # Корректно вычисляем процент
                if total_deals > 0:
                    percent = round(deals_count / total_deals * 100, 1)
                else:
                    percent = 0
                
                # Добавляем данные по этапу
                stages_data.append({
                    'id': stage.id,
                    'name': stage.name,
                    'color': stage.color or '#3498db',
                    'deals_count': deals_count,
                    'open_deals': open_deals,
                    'closed_deals': closed_deals,
                    'deals_amount': deals_amount,
                    'success_amount': success_amount,
                    'is_success_stage': stage.type == 'success',
                    'percent': percent
                })
                
                total_amount += deals_amount
                total_open_deals += open_deals
                total_closed_deals += closed_deals
                total_success_amount += success_amount
            
            # Статистика по закрытым сделкам с учетом фильтра по году
            won_filter = deals_filter.copy()
            won_filter.update({
                'is_closed': True, 
                'stage__type': 'success'
            })
            won_deals = Deal.objects.filter(**won_filter).count()
            
            lost_filter = deals_filter.copy()
            lost_filter.update({
                'is_closed': True, 
                'stage__type': 'failure'
            })
            lost_deals = Deal.objects.filter(**lost_filter).count()
            
            # Среднее время закрытия сделки (в днях) с учетом фильтра по году
            avg_filter = deals_filter.copy()
            avg_filter.update({
                'is_closed': True, 
                'created_at__isnull': False,
                'closed_at__isnull': False
            })
            avg_deal_lifetime_query = Deal.objects.filter(**avg_filter).annotate(
                lifetime=ExpressionWrapper(
                    F('closed_at') - F('created_at'), 
                    output_field=DurationField()
                )
            ).aggregate(avg=Avg('lifetime'))
            
            avg_deal_lifetime = avg_deal_lifetime_query['avg']
            
            # Преобразуем timedelta в дни
            if avg_deal_lifetime:
                avg_deal_lifetime = avg_deal_lifetime.total_seconds() // 86400
            else:
                avg_deal_lifetime = 0
            
            # Добавляем данные по воронке
            dashboard_data.append({
                'id': pipeline.id,
                'name': pipeline.name,
                'is_main': pipeline.is_main,
                'stages': stages_data,
                'stage_types': stage_types_list,
                'total_deals': total_deals,
                'total_amount': total_amount,
                'total_success_amount': total_success_amount,
                'open_deals': total_open_deals,
                'closed_deals': total_closed_deals,
                'won_deals': won_deals,
                'lost_deals': lost_deals,
                'conversion_rate': round(won_deals / max(won_deals + lost_deals, 1) * 100, 1),
                'avg_deal_lifetime': avg_deal_lifetime
            })
        
        context = {
            'dashboard_data': dashboard_data,
            'last_sync': Deal.objects.order_by('-last_sync').first().last_sync if Deal.objects.exists() else None,
            'selected_year': selected_year,
            'available_years': available_years,
            'settings': settings  # Передаем настройки в шаблон
        }
        
        return render(request, 'crm_connector/pipelines_dashboard.html', context)
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        context = {
            'error': str(e),
            'error_details': error_details if settings.DEBUG else None
        }
        return render(request, 'crm_connector/error.html', context)

@csrf_protect
def import_deals_from_excel(request):
    """Представление для импорта сделок из Excel файла"""
    if not request.user.is_authenticated:
        messages.warning(request, 'Для импорта данных необходимо войти в систему.')
        return redirect(f'{settings.LOGIN_URL}?next={request.path}')
    
    bitrix_pipeline_id = 11  # Bitrix ID воронки РОИВ
    
    # Подключаемся к API для получения справочников
    try:
        api = Bitrix24API()
        industries = api.get_company_industries()
        company_types = api.get_company_types()
        pipeline_stages = api.get_pipeline_stages(bitrix_pipeline_id)
        
        # Выводим отладочную информацию
        logger.debug(f"Получено {len(industries)} отраслей, {len(company_types)} типов компаний, {len(pipeline_stages)} стадий воронки")
        
        # Создаем словарь соответствия названий стадий их ID
        global_stages_map = {}
        for stage_id, stage_name in pipeline_stages:
            global_stages_map[stage_name] = stage_id
            
    except Exception as e:
        logger.error(f"Ошибка при получении справочников из Битрикс24: {str(e)}")
        messages.warning(request, f"Не удалось загрузить справочники из Битрикс24: {str(e)}")
        industries = []
        company_types = []
        pipeline_stages = []
        global_stages_map = {}
    
    if request.method == 'POST':
        # Передаем справочники в форму
        form = ExcelImportForm(
            request.POST, 
            request.FILES, 
            industries=industries, 
            company_types=company_types
        )
        
        if form.is_valid():
            try:
                excel_file = request.FILES['excel_file']
                business_sphere = form.cleaned_data['business_sphere']
                organization_type = form.cleaned_data['organization_type']
                
                # Чтение Excel-файла
                df = pd.read_excel(excel_file)
                
                # Счетчики для статистики
                contacts_created = 0
                contacts_existing = 0
                companies_created = 0
                companies_existing = 0
                deals_created = 0
                errors = 0
                
                # При обработке каждой строки Excel используем словарь соответствия стадий
                for index, row in df.iterrows():
                    try:
                        # Получаем данные из строки
                        organization_name = str(row.get('Название организации', '')).strip()
                        organization_type_from_excel = str(row.get('Вид организации', '')).strip()
                        deal_stage = str(row.get('Стадия сделки', '')).strip()
                        region = str(row.get('Регион', '')).strip()
                        manager_name = str(row.get('ФИО руководителя организации', '')).strip()
                        manager_position = str(row.get('Должность руководителя', '')).strip()
                        input_number = str(row.get('Входной номер', '')).strip()
                        input_type = str(row.get('Тип входного номера', '')).strip()
                        education_direction = str(row.get('Направление обучения', '')).strip()
                        education_program = str(row.get('Программа обучения', '')).strip()
                        contact_name = str(row.get('ФИО Контактного лица', '')).strip()
                        contact_phone = str(row.get('Телефон Контактного лица', '')).strip()
                        contact_email = str(row.get('Почта Контактного лица', '')).strip()
                        lists_received = str(row.get('Фактически получено списков', '')).strip()
                        
                        # Если нет названия организации, пропускаем строку
                        if not organization_name:
                            continue
                        
                        # 1. Создаем или находим контакт
                        contact_data = {
                            'NAME': contact_name.split()[0] if contact_name and len(contact_name.split()) > 0 else '',
                            'LAST_NAME': ' '.join(contact_name.split()[1:]) if contact_name and len(contact_name.split()) > 1 else '',
                            'TYPE_ID': 'CURATOR',  # Тип контакта по умолчанию "куратор"
                            'PHONE': [{'VALUE': contact_phone, 'VALUE_TYPE': 'WORK'}] if contact_phone else [],
                            'EMAIL': [{'VALUE': contact_email, 'VALUE_TYPE': 'WORK'}] if contact_email else [],
                            'COMMENTS': f'Регион: {region}' if region else '',
                        }
                        
                        # Проверяем, существует ли контакт
                        existing_contact = None
                        if contact_email:
                            existing_contacts = api.find_contact_by_email(contact_email)
                            if existing_contacts:
                                existing_contact = existing_contacts[0]
                        
                        if not existing_contact and contact_phone:
                            existing_contacts = api.find_contact_by_phone(contact_phone)
                            if existing_contacts:
                                existing_contact = existing_contacts[0]
                        
                        contact_id = None
                        if existing_contact:
                            contact_id = existing_contact['ID']
                            # Обновляем существующий контакт
                            api.update_contact(contact_id, contact_data)
                            contacts_existing += 1
                        else:
                            # Создаем новый контакт
                            contact_result = api.add_contact(contact_data)
                            contact_id = contact_result
                            contacts_created += 1
                        
                        # 2. Создаем или находим компанию
                        company_data = {
                            'TITLE': organization_name,
                            'COMPANY_TYPE': organization_type,  # Тип организации из формы
                            'INDUSTRY': business_sphere,  # Сфера деятельности из формы
                            'COMMENTS': f'Вид организации: {organization_type_from_excel}\nРегион: {region}',
                            'ADDRESS': region,
                            'OPENED': 'Y',
                            'ASSIGNED_BY_ID': request.user.id  # ID текущего пользователя как ответственного
                        }
                        
                        # Проверяем, существует ли компания
                        existing_companies = api.find_company_by_name(organization_name)
                        company_id = None
                        
                        if existing_companies:
                            company_id = existing_companies[0]['ID']
                            # Обновляем существующую компанию
                            api.update_company(company_id, company_data)
                            companies_existing += 1
                        else:
                            # Создаем новую компанию
                            company_result = api.add_company(company_data)
                            company_id = company_result
                            companies_created += 1
                        
                        # 3. Создаем сделку
                        deal_data = {
                            'TITLE': f"Заявка от {organization_name}",
                            'CATEGORY_ID': str(bitrix_pipeline_id),
                            'STAGE_ID': map_stage_to_bitrix_id(deal_stage, global_stages_map),
                            'COMPANY_ID': company_id,
                            'CONTACT_ID': contact_id,  # Основной контакт сделки
                            'OPENED': 'Y',
                            'ASSIGNED_BY_ID': request.user.id,  # ID текущего пользователя как ответственного
                            'COMMENTS': f"""
                            Руководитель: {manager_name}
                            Должность: {manager_position}
                            Входной номер: {input_number}
                            Тип входного номера: {input_type}
                            Направление обучения: {education_direction}
                            Программа обучения: {education_program}
                            Фактически получено списков: {lists_received}
                            """,
                            'BEGINDATE': timezone.now().strftime('%Y-%m-%d'),
                            'REGION': region,
                            # Добавляем пользовательские поля
                            'UF_CRM_EDUCATION_DIRECTION': education_direction,
                            'UF_CRM_EDUCATION_PROGRAM': education_program,
                            'UF_CRM_INPUT_NUMBER': input_number,
                            'UF_CRM_INPUT_TYPE': input_type,
                            'UF_CRM_LISTS_RECEIVED': lists_received
                        }
                        
                        # Создаем сделку
                        deal_result = api.add_deal(deal_data)
                        
                        if deal_result:
                            deals_created += 1
                        
                    except Exception as e:
                        errors += 1
                        logger.error(f"Ошибка при обработке строки {index+1}: {str(e)}")
                
                # Формируем сообщение с результатами
                result_message = f"""
                Импорт завершен. Результаты:
                - Создано новых контактов: {contacts_created}
                - Обновлено существующих контактов: {contacts_existing}
                - Создано новых организаций: {companies_created}
                - Обновлено существующих организаций: {companies_existing}
                - Создано сделок: {deals_created}
                - Ошибок: {errors}
                """
                
                messages.success(request, result_message)
                return redirect('crm_connector:pipelines_dashboard')
                
            except Exception as e:
                messages.error(request, f'Ошибка при импорте: {str(e)}')
                return redirect('crm_connector:import_deals')
    else:
        # Передаем справочники в пустую форму
        form = ExcelImportForm(industries=industries, company_types=company_types)
    
    # Передаем в шаблон актуальные стадии воронки для информации пользователю
    return render(request, 'crm_connector/import_deals.html', {
        'form': form,
        'pipeline_stages': pipeline_stages
    })

def map_stage_to_bitrix_id(stage_name, stages_map=None):
    """Преобразует текстовое название стадии в ID стадии Битрикс24"""
    # Используем переданный словарь стадий, если он есть
    if stages_map and stage_name in stages_map:
        return stages_map[stage_name]
    
    # Если словаря нет или стадии нет в словаре, используем стандартный формат
    # для воронки с ID=11 в Битрикс24
    default_stages_map = {
        'Первичный контакт': 'C11:NEW',  # Формат: C<ID воронки>:<код стадии>
        'Переговоры': 'C11:PREPARATION',
        'Составление списков': 'C11:EXECUTING',
        'Согласование списков': 'C11:FINAL_INVOICE',
        'Списки согласованы': 'C11:WON',
        'Сделка отменена': 'C11:LOSE'
    }
    
    # Возвращаем ID стадии, если такая стадия есть в словаре, иначе ID стадии "Первичный контакт"
    return default_stages_map.get(stage_name, 'C11:NEW')

@csrf_protect
def import_atlas_applications(request):
    """Представление для импорта заявок из выгрузки Атласа"""
    if not request.user.is_authenticated:
        messages.warning(request, 'Для импорта данных необходимо войти в систему.')
        return redirect(f'{settings.LOGIN_URL}?next={request.path}')
    
    import_summary = None  # Сюда поместим итоговый текст результатов импорта
    stage_result = None

    # Определяем формы по умолчанию
    excel_form = ExcelImportForm(initial={'pipeline_name': 'Заявки (граждане)'})
    stage_form = StageCheckForm()

    if request.method == 'POST':
        # Определяем, какая форма отправлена

        if 'check_stage' in request.POST:
            # Обработка формы проверки стадии
            stage_form = StageCheckForm(request.POST)
            if stage_form.is_valid():
                atlas_status = stage_form.cleaned_data.get('atlas_status')
                rr_status = stage_form.cleaned_data.get('rr_status')

                # Находим воронку (основную или по названию)
                pipeline = Pipeline.get_main_pipeline() or Pipeline.objects.filter(name='Заявки (граждане)').first()

                # используем общую функцию
                mapping_file = os.path.join(os.path.dirname(__file__), 'atlas_field_mapping.json')
                try:
                    with open(mapping_file, 'r', encoding='utf-8') as f:
                        mapping_conf = json.load(f)
                except Exception:
                    mapping_conf = {}

                from crm_connector.utils import determine_stage_for_statuses
                stage_id = determine_stage_for_statuses(pipeline, atlas_status, rr_status, mapping_conf)
                
                if stage_id:
                    # Ищем стадию по ID чтобы получить её название
                    try:
                        stage = Stage.objects.get(bitrix_id=stage_id)
                        stage_result = f'{stage.name} (ID: {stage_id})'
                    except Stage.DoesNotExist:
                        stage_result = f'Стадия с ID {stage_id} не найдена в базе данных'
                else:
                    stage_result = 'Не удалось определить стадию'

        else:
            # Форма импорта Excel
            excel_form = ExcelImportForm(request.POST, request.FILES)
            # Сделаем необязательными поля, которые не используются в этой форме
            for optional_field in ('business_sphere', 'organization_type'):
                if optional_field in excel_form.fields:
                    excel_form.fields[optional_field].required = False

            if excel_form.is_valid():
                try:
                    excel_file = request.FILES['excel_file']
                    pipeline_name = excel_form.cleaned_data.get('pipeline_name', 'Заявки (граждане)')

                    # Сохраняем файл временно
                    import tempfile, os as _os
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                        for chunk in excel_file.chunks():
                            tmp_file.write(chunk)
                        tmp_file_path = tmp_file.name

                    try:
                        from django.core.management import call_command
                        from io import StringIO
                        out = StringIO()
                        call_command('import_atlas_applications', tmp_file_path, f'--pipeline-name={pipeline_name}', stdout=out)
                        result_output = out.getvalue().split('\n')
                        keywords = ['Обновлено сделок', 'Удалено', 'Найдено совпадений', 'Новых заявок', 'Обновлено существующих сделок', 'Создано новых сделок', 'Ошибок:']
                        important_lines = [l.strip() for l in result_output if any(k in l for k in keywords) and l.strip()]
                        import_summary = '\n'.join(important_lines) if important_lines else '\n'.join(result_output)
                    finally:
                        _os.unlink(tmp_file_path)

                    # после импорта сбрасываем форму
                    excel_form = ExcelImportForm(initial={'pipeline_name': pipeline_name})
                    for optional_field in ('business_sphere', 'organization_type'):
                        if optional_field in excel_form.fields:
                            excel_form.fields[optional_field].required = False
                except Exception as e:
                    logger.error(f"Ошибка при импорте заявок из Атласа: {str(e)}")
                    messages.error(request, f'Ошибка при импорте: {str(e)}')
                    return redirect('crm_connector:import_atlas_applications')
    # For GET we already have excel_form and stage_form default
    
    # Получаем статистику по последнему импорту
    last_import = AtlasApplication.objects.order_by('-created_at').first()
    
    context = {
        'form': excel_form,
        'stage_form': stage_form,
        'last_import': last_import,
        'total_applications': AtlasApplication.objects.count(),
        'synced_applications': AtlasApplication.objects.filter(is_synced=True).count(),
        'pending_applications': AtlasApplication.objects.filter(is_synced=False).count(),
        'import_summary': import_summary,
        'stage_result': stage_result,
    }
    
    return render(request, 'crm_connector/import_atlas_applications.html', context)

def import_not_atlas(request):
    import re;
    if request.method == 'POST':
        form = LeadImportForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = form.cleaned_data['excel_file']
            edcuationdirection = form.cleaned_data['training']

            try:
                wb = openpyxl.load_workbook(excel_file)
                ws = wb.active
            except Exception as e:
                messages.error(request, f'Ошибка при открытии файла: {e}')
                return render(request, 'crm_connector/import_lids.html', {'form': form})

            missing_company_rows = []
            missing_name_rows = []
            missing_phone_rows = []

            for row in ws.iter_rows(min_row=2, values_only=True):
                ExcelPhone = row[3]
                contact_name = row[2]
                contact_phone = row[3]
                contact_email = row[4]
                CompanyStringList = str(row[1]).split() # Тут убрать лишние пробелы надо
                company_name = ' '.join(CompanyStringList)   # Поэтому эти две строки существуют
                # Проверка обязательных полей
                if not row[1] and row[0] != None:
                    missing_company_rows.append(int(row[0])) # Собираем номера полей, где нет компании
                    continue
                if contact_name is None and row[0] != None:
                    missing_name_rows.append(int(row[0])) # Собираем номера полей, где нет ФИО
                    continue
                if not row[3] and row[0] != None:
                    missing_phone_rows.append(int(row[0])) # Собираем номера полей, где нет телефона
                    continue
                # Проверка эмейла на вшивость
                pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if re.match(pattern, str(row[4])):
                    contact_email = row[4]
                else:
                    contact_email = ''
                # Проверка телефона на вшивость
                if isinstance(ExcelPhone, float):
                    if ExcelPhone.is_integer():
                        ExcelPhone = str(int(ExcelPhone))
                    else:
                        ExcelPhone = str(ExcelPhone)
                else:
                    ExcelPhone = str(ExcelPhone).strip()
                ExcelPhone = re.sub(r'\D','',ExcelPhone)
                if ExcelPhone.startswith('7'):
                    ExcelPhone = '8' + ExcelPhone[1:]
                
                # Создаем лид с status=0 и текущим временем создания
                api = Bitrix24API()
                contact_data = {
                    'NAME': contact_name.split()[0] if contact_name and len(contact_name.split()) > 0 else '',
                    'LAST_NAME': ' '.join(contact_name.split()[1:]) if contact_name and len(contact_name.split()) > 1 else '',
                    'TYPE_ID': 'CURATOR',  # Тип контакта по умолчанию "куратор"
                    'PHONE': [{'VALUE': contact_phone, 'VALUE_TYPE': 'WORK'}] if contact_phone else [],
                    'EMAIL': [{'VALUE': contact_email, 'VALUE_TYPE': 'WORK'}] if contact_email else []
                }

                # Проверяем, существует ли контакт
                existing_contact = None
                if contact_email:
                    existing_contacts = api.find_contact_by_email(contact_email)
                    if existing_contacts:
                        existing_contact = existing_contacts

                if not existing_contact and contact_phone:
                    existing_contacts = api.find_contact_by_phone(contact_phone)
                    if existing_contacts:
                        existing_contact = existing_contacts

                contact_id = None
                if existing_contact:
                    contact_id = existing_contact['ID']
                    # Обновляем существующий контакт
                    api.update_contact(contact_id, contact_data)
                else:
                    # Создаем новый контакт
                    contact_result = api.add_contact(contact_data)
                    contact_id = contact_result

                # 2. Создаем или находим компанию
                company_data = {
                    'TITLE': company_name,
                    'OPENED': 'Y',
                    }
                            
                        # Проверяем, существует ли компания
                existing_companies = api.find_company_by_name(company_name)
                company_id = None
                            
                if existing_companies:
                    company_id = existing_companies['ID']
                                # Обновляем существующую компанию
                    api.update_company(company_id, company_data)
                else:
                                # Создаем новую компанию
                    company_result = api.add_company(company_data)
                    company_id = company_result

                lead_data = {
                        'TITLE': company_name,
                        'CATEGORY_ID': '11',
                        'COMPANY_ID': company_id,
                        'CONTACT_ID': contact_id,
                        # Указание направления обучения
                        'UF_CRM_1741091080288': edcuationdirection
                    }
                api.add_deal(lead_data)
            messages.success(request, 'Сделки успешно импортированы')
            if missing_company_rows:
                messages.warning(request, f'Пропущены строки из-за неуказанной компании: {",".join(map(str, missing_company_rows))}')
            if missing_name_rows:
                messages.warning(request, f'Пропущены строки из-за неуказанного ФИО: {",".join(map(str, missing_name_rows))}')
            if missing_phone_rows:
                messages.warning(request, f'Пропущены строки из-за неуказанного телефона: {",".join(map(str, missing_phone_rows))}')
            
    else:
        form = LeadImportForm()

    return render(request, 'crm_connector/import_not_atlas.html', {'form': form})

from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404

from .forms import StageCheckForm
import json, os

class ObjectHistoryView(LoginRequiredMixin, ListView):
    """Представление для просмотра истории изменений объекта"""
    template_name = 'crm_connector/history_view.html'
    context_object_name = 'history'
    paginate_by = 50
    
    def get_object(self):
        """Получает объект для которого показывается история"""
        model_name = self.kwargs['model']
        pk = self.kwargs['pk']
        
        model_map = {
            'deal': Deal,
            'pipeline': Pipeline,
            'stage': Stage,
            'atlasapplication': AtlasApplication,
        }
        
        model_class = model_map.get(model_name.lower())
        if not model_class:
            raise Http404("Модель не найдена")
            
        return get_object_or_404(model_class, pk=pk)
    
    def get_queryset(self):
        """Возвращает историю изменений для объекта"""
        obj = self.get_object()
        return obj.history.all()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()
        
        context['object'] = obj
        context['model_name'] = obj.__class__.__name__.lower()
        context['model_verbose_name'] = obj.__class__._meta.verbose_name
        
        # Получаем поля модели для отображения в деталях
        excluded_fields = ['history_id', 'history_date', 'history_change_reason', 
                          'history_user', 'history_type', 'history_object']
        fields = []
        
        for field in obj._meta.fields:
            if field.name not in excluded_fields:
                fields.append({
                    'name': field.name,
                    'verbose_name': field.verbose_name
                })
        
        context['fields'] = fields
        
        return context

def lead_dashboard(request):
    # Список нужных кодов стейджей
    needed_stage_codes = [
        'NEW',
        'UC_OHS476',
        'PREPARATION',
        'EXECUTING',
        'UC_6HMXDA',
        'UC_82NA5G',
        'UC_WCW6RM',
        'WON',
        'LOSE',
    ]
    query = Q()
    for code in needed_stage_codes:
        query |= Q(bitrix_id__icontains=code)
    # Загружаем стадии с такими кодами
    stages = Stage.objects.filter(query).order_by('bitrix_id')
    stage_id_to_code = {stage.bitrix_id: stage.name for stage in stages}
    stage_code_to_name = {
        'NEW': '1. Необработанная заявка',
        'UC_OHS476': '2. Направлена инструкция по РвР',
        'PREPARATION': '3. Подал заявки на РвР',
        'EXECUTING': '4. Заявка на обучение одобрена',
        'UC_6HMXDA': '5. Заключен 3-сторонний договор',
        'UC_82NA5G': '6. Заключен договор на обучение',
        'UC_WCW6RM': '7. Приступил к обучению',
        'WON': '8. Прошел итоговую аттестацию',
        'LOSE': '9. Отказ',
    }
    
    for stage in stages:
        query |= Q(stage__bitrix_id__icontains=stage.bitrix_id)
    # Получаем сделки с требуемыми стейджами
    deals = Deal.objects.filter(query).select_related('company', 'stage')

    # Формируем словарь: {программа: {регион: {компания: {stage_code: count, ..., 'total': count}}}}
    data = {}
    program_totals = {}
    region_totals = {}
    total = {code:0 for code in needed_stage_codes}
    headcompanies = {}

    # Заполняем словарь родительских компаний
    for deal in deals:
        head = deal.company.head
        try:
            int(head)
            Company.objects.get(bitrix_id = head).title
        except:
            head = ''
        if head:
            try:
                headcompanies[head] = Company.objects.get(bitrix_id = deal.company.head).title
            except Exception as e:
                logger.error(f"Не удалось найти родительскую компаниню: {e}")

    for deal in deals:
        prog = deal.get_program_display() if hasattr(deal, 'get_program_display') else deal.program
        region = deal.get_region_display() if hasattr(deal, 'get_region_display') else deal.region
        headid = deal.company.head
        try:
            int(headid)
        except:
            headid = ''
        if prog and region != '':
            company_name = deal.company.title if deal.company else 'Без компании'
            stage_code = deal.stage.bitrix_id
            for code in needed_stage_codes:
                if code in stage_code:
                    stage_code = code
            
            data.setdefault(prog, {})
            data[prog].setdefault(region, {})
            if headid:
                data[prog][region].setdefault(headcompanies[headid], {code: 0 for code in needed_stage_codes})
                data[prog][region][headcompanies[headid]].setdefault('total', 0)
                data[prog][region][headcompanies[headid]].setdefault('child', {})
                data[prog][region][headcompanies[headid]]['total'] +=1
                data[prog][region][headcompanies[headid]][stage_code] +=1
                data[prog][region][headcompanies[headid]]['child'].setdefault(company_name, {code:0 for code in needed_stage_codes})
                data[prog][region][headcompanies[headid]]['child'][company_name].setdefault('total', 0)
                data[prog][region][headcompanies[headid]]['child'][company_name][stage_code] += 1
                data[prog][region][headcompanies[headid]]['child'][company_name]['total'] += 1
            else:
                data[prog][region].setdefault(company_name, {code:0 for code in needed_stage_codes})
                data[prog][region][company_name].setdefault('total',0)
                data[prog][region][company_name][stage_code] += 1
                data[prog][region][company_name]['total'] += 1



            # Подсчёт общего количества сделок по программе
            program_totals.setdefault(prog, {code: 0 for code in needed_stage_codes})
            program_totals[prog].setdefault('total', 0)
            program_totals[prog][stage_code] += 1
            program_totals[prog]['total'] += 1

            # Подсчёт общего количества сделок по региону
            # Можно считать отдельно по (программа, регион) для точности:
            region_totals.setdefault(prog, {})
            region_totals[prog].setdefault(region, {code: 0 for code in needed_stage_codes})
            region_totals[prog][region].setdefault('total',0)
            region_totals[prog][region]['total'] += 1
            region_totals[prog][region][stage_code] += 1

            total.setdefault('total',0)
            total['total'] +=1
            total[stage_code] +=1

    context = {
        'data': data,
        'stage_codes': needed_stage_codes,
        'stage_code_to_name': stage_code_to_name,
        'program_totals': program_totals,
        'region_totals': region_totals,
        'total': total
    }
    # return JsonResponse({'result': context})
    return render(request, 'crm_connector/lead-dashboard.html', context)


def atlas_dashboard(request):
    """Дашборд для заявок из Атласа с визуализацией по этапам, программам и регионам"""
    from django.db.models import Q
    from datetime import datetime, timedelta
    
    # Получаем параметры фильтрации из запроса
    selected_program = request.GET.get('program', '')
    selected_region = request.GET.get('region', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    # Получаем воронку "Заявки (граждане)"
    pipeline = Pipeline.objects.filter(name='Заявки (граждане)').first()
    if not pipeline:
        # Если воронка не найдена, возвращаем пустую страницу
        return render(request, 'crm_connector/atlas_dashboard.html', {'error': 'Воронка "Заявки (граждане)" не найдена'})
    
    # Получаем все сделки из этой воронки
    deals = Deal.objects.select_related('stage').filter(pipeline=pipeline).exclude(stage__name__in=['1. Необработанная заявка', '2. Направлена инструкция по РвР'])
    
    # Получаем связанные AtlasApplication для фильтрации
    # Создаем словарь сделка -> заявка для быстрого доступа
    atlas_apps_dict = {}
    atlas_apps = AtlasApplication.objects.select_related('deal').filter(deal__pipeline=pipeline)
    for app in atlas_apps:
        atlas_apps_dict[app.deal_id] = app
    
    # Применяем фильтры через AtlasApplication, если они есть
    if selected_program or selected_region or (start_date and end_date):
        # Фильтруем AtlasApplication
        filtered_apps = atlas_apps
        
        if selected_program:
            filtered_apps = filtered_apps.filter(
                Q(raw_data__icontains=f'"Программа обучения": "{selected_program}"') |
                Q(raw_data__icontains=f'"Направление обучения": "{selected_program}"')
            )
        
        if selected_region:
            filtered_apps = filtered_apps.filter(region=selected_region)
        
        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d')
                filtered_apps = filtered_apps.filter(
                    Q(raw_data__icontains=f'"Начало периода обучения"') &
                    Q(created_at__gte=start) &
                    Q(created_at__lte=end)
                )
            except ValueError:
                pass
        
        # Получаем ID сделок из отфильтрованных заявок
        deal_ids = filtered_apps.values_list('deal_id', flat=True)
        deals = deals.filter(id__in=deal_ids)
    
    # Получаем все этапы воронки для правильного порядка и типов
    stages_db = Stage.objects.filter(pipeline=pipeline).order_by('sort')
    if stages_db.exists():
        # Создаем словарь этапов с информацией о типе и порядке
        stages_info = {}
        ordered_stages = []
        rejected_stages = []
        
        # Этапы, которые нужно скрыть из отображения
        # Закомментировано для отображения всех этапов
        hidden_stages = [
            '1. Необработанная заявка',
            '2. Направлена инструкция по РвР'
        ]
        
        for stage in stages_db:
            # Пропускаем скрытые этапы - закомментировано
            if stage.name in hidden_stages:
                continue
                
            stages_info[stage.name] = {
                'type': stage.type,
                'color': stage.color,
                'sort': stage.sort,
                'bitrix_id': stage.bitrix_id
            }
            
            if stage.name not in hidden_stages and stage.type != 'failure':
                ordered_stages.append(stage.name)
            
            if stage.type == 'failure':
                rejected_stages.append(stage.name)
        
        # НЕ добавляем колонку "Отказы" - показываем все этапы отдельно
        ordered_stages.append('Отказы')
        stages_info['Отказы'] = {
            'type': 'failure',
            'color': '#d9534f',
            'sort': 1000,
            'bitrix_id': 'REJECTED'
        }
    else:
        stages_info = {}
        ordered_stages = []
        rejected_stages = []
    
    # Агрегация данных по этапам сделок
    stage_stats = {}
    # Инициализируем все этапы
    for stage_name in ordered_stages:
        stage_stats[stage_name] = {
            'total': 0,
            'by_program': {},
            'by_region': {},
            'by_period': {}
        }
    
    # Подготовка данных для недельного графика по дате подачи заявки на РР
    weekly_data = {}
    # Подготовка данных для календарных недель (понедельник-воскресенье)
    today = datetime.now().date()
    # Находим понедельник текущей недели
    start_of_week = today - timedelta(days=today.weekday())
    
    weeks = []
    for i in range(5):
        week_start_date = start_of_week - timedelta(weeks=i)
        week_end_date = week_start_date + timedelta(days=6)
        week_label = f"{week_start_date.strftime('%d.%m')} - {week_end_date.strftime('%d.%m.%Y')}"
        weeks.append({
            'label': week_label,
            'start': week_start_date,
            'end': week_end_date,
            'count': 0
        })
    weeks.reverse()  # Чтобы самая ранняя неделя была первой
    
    for deal in deals:
        if deal.stage:
            stage_name = deal.stage.name
            
            # НЕ группируем отказные этапы - показываем каждый отдельно
            if stage_name in rejected_stages:
                stage_name = 'Отказы'
            
            if stage_name not in stage_stats:
                continue
            
            stage_stats[stage_name]['total'] += 1
            
            # Проверяем, есть ли связанная AtlasApplication
            atlas_app = atlas_apps_dict.get(deal.id)
            
            if atlas_app:
                # Извлекаем данные из raw_data
                raw_data = atlas_app.raw_data or {}
                program = raw_data.get('Программа обучения', 'Не указана')
                region = atlas_app.region or 'Не указан'
                period_start = raw_data.get('Начало периода обучения', '')
                period_end = raw_data.get('Окончание периода обучения', '')
                rr_submission_date = raw_data.get('Дата подачи заявки на РР', '')
                
                # Подсчет для недельного графика
                if rr_submission_date:
                    try:
                        # Обновляем формат даты
                        submission_dt = datetime.strptime(rr_submission_date, '%d.%m.%Y %H:%M:%S')
                        submission_date = submission_dt.date()
                        for week in weeks:
                            if week['start'] <= submission_date <= week['end']:
                                week['count'] += 1
                                break
                    except ValueError:
                        pass
            else:
                # Для сделок без AtlasApplication используем значения по умолчанию
                program = 'Не указана'
                region = 'Не указан'
                period = 'Период не указан'
                period_start = ''
                period_end = ''
            
            # Группировка по программе
            if program not in stage_stats[stage_name]['by_program']:
                stage_stats[stage_name]['by_program'][program] = 0
            stage_stats[stage_name]['by_program'][program] += 1
            
            # Группировка по региону
            if region not in stage_stats[stage_name]['by_region']:
                stage_stats[stage_name]['by_region'][region] = 0
            stage_stats[stage_name]['by_region'][region] += 1
            
            # Группировка по периоду
            if period_start and period_end:
                period = f"{period_start} - {period_end}"
            else:
                period = "Период не указан"
            
            if period not in stage_stats[stage_name]['by_period']:
                stage_stats[stage_name]['by_period'][period] = 0
            stage_stats[stage_name]['by_period'][period] += 1
    
    # Получаем уникальные программы, регионы и периоды для фильтров
    all_programs = set()
    all_regions = set()
    all_periods = set()
    
    for app in AtlasApplication.objects.all():
        raw_data = app.raw_data or {}
        program = raw_data.get('Программа обучения')
        if program:
            all_programs.add(program)
        if app.region:
            all_regions.add(app.region)
        
        period_start = raw_data.get('Начало периода обучения', '')
        period_end = raw_data.get('Окончание периода обучения', '')
        if period_start and period_end:
            all_periods.add(f"{period_start} - {period_end}")
    
    # Сортируем списки для удобства
    all_programs = sorted(list(all_programs))
    all_regions = sorted(list(all_regions))
    all_periods = sorted(list(all_periods))
    
    # Общая статистика
    total_applications = deals.count()
    # Подсчитываем активные заявки (исключая отказы)
    active_applications = sum(stage_stats[stage]['total'] for stage in ordered_stages if stage != 'Отказы')
    
    # Подготовка данных для графиков (JSON)
    import json
    
    # Данные для круговой диаграммы по этапам (в правильном порядке)
    stages_chart_data = {
        'labels': ordered_stages,
        'data': [stage_stats[stage]['total'] for stage in ordered_stages]
    }
    
    # Данные для недельного графика
    weekly_chart_data = {
        'labels': [week['label'] for week in weeks],
        'data': [week['count'] for week in weeks]
    }
    
    # Данные для столбчатой диаграммы по программам
    programs_data = {}
    program_totals = {}
    for stage_name, stage_data in stage_stats.items():
        for program, count in stage_data['by_program'].items():
            if program not in programs_data:
                programs_data[program] = {}
                program_totals[program] = 0
            programs_data[program][stage_name] = count
            program_totals[program] += count
    
    # Данные для таблицы по регионам
    regions_data = {}
    region_totals = {}
    for stage_name, stage_data in stage_stats.items():
        for region, count in stage_data['by_region'].items():
            if region not in regions_data:
                regions_data[region] = {}
                region_totals[region] = 0
            regions_data[region][stage_name] = count
            region_totals[region] += count
    
    # Создаем иерархическую структуру: программа -> регионы с периодами
    hierarchical_data = {}
    for deal in deals:
        if deal.stage:
            stage_name = deal.stage.name
            
            # НЕ группируем отказные этапы
            if stage_name in rejected_stages:
                stage_name = 'Отказы'
            # НЕ пропускаем этапы
            if stage_name in hidden_stages:
                continue
            
            # Проверяем, есть ли связанная AtlasApplication
            atlas_app = atlas_apps_dict.get(deal.id)
            
            if atlas_app:
                raw_data = atlas_app.raw_data or {}
                program = raw_data.get('Программа обучения', 'Не указана')
                region = atlas_app.region or 'Не указан'
                
                # Извлекаем период обучения
                period_start = raw_data.get('Начало периода обучения', '')
                period_end = raw_data.get('Окончание периода обучения', '')
                if period_start and period_end:
                    period = f"{period_start} - {period_end}"
                else:
                    period = "Период не указан"
            else:
                # Для сделок без AtlasApplication
                program = 'Не указана'
                region = 'Не указан'
                period = 'Период не указан'
            
            # Создаем уникальный ключ для региона + период
            region_period_key = f"{region}|{period}"
            
            if program not in hierarchical_data:
                hierarchical_data[program] = {
                    'total': {},
                    'region_periods': {}
                }
                # Инициализируем все этапы для программы
                for stage in ordered_stages:
                    hierarchical_data[program]['total'][stage] = 0
            
            if region_period_key not in hierarchical_data[program]['region_periods']:
                hierarchical_data[program]['region_periods'][region_period_key] = {
                    'region': region,
                    'period': period,
                    'stages': {}
                }
                # Инициализируем все этапы для региона+периода
                for stage in ordered_stages:
                    if stage in rejected_stages:
                        stage = 'Отказы'
                    hierarchical_data[program]['region_periods'][region_period_key]['stages'][stage] = 0
            
            # Увеличиваем счетчики
            hierarchical_data[program]['total'][stage_name] += 1
            hierarchical_data[program]['region_periods'][region_period_key]['stages'][stage_name] += 1
    
    context = {
        'total_applications': total_applications,
        'active_applications': active_applications,
        'stage_stats': stage_stats,
        'stages_chart_data': json.dumps(stages_chart_data, ensure_ascii=False),
        'weekly_chart_data': json.dumps(weekly_chart_data, ensure_ascii=False),
        'programs_data': programs_data,
        'program_totals': program_totals,
        'regions_data': regions_data,
        'region_totals': region_totals,
        'hierarchical_data': hierarchical_data,
        'ordered_stages': ordered_stages,
        'stages_info': stages_info,
        'all_programs': all_programs,
        'all_regions': all_regions,
        'all_periods': all_periods,
        'selected_program': selected_program,
        'selected_region': selected_region,
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'crm_connector/atlas_dashboard.html', context)
 


def attestation_progress(request):
    education_products = {
        'Инструменты искусственного интеллекта в сфере культуры': {
            1: "Введение в ИИ в сфере культуры",
            2: "Работа с большими языковыми моделями",
            3: "Работа с диффузионными нейросетями",
            4: "ИИ в исследовании и аналитике",
            5: "Виртуальные ассистенты и чат-боты в сфере культуры"
        },
        'Специалист по эксплуатации беспилотных авиационных систем в сфере лесного хозяйства': {
            1: "Введение в БАС. БАС в правовом поле(Аттестация)",
            2: "2.1 Техническое обслуживание БАС",
            3: "2.2 Диагностика и устранение неисправностей",
            4: "2.3 Профилактика поломок и продление срока службы БАС",
            5: "Обслуживание и ремонт БАС(Аттестация)",
            6: "Основы управления и пилотрования БАС(Аттестация)",
            7: "Применение БАС для решения задач в деятельности лесных хозяйств(Аттестация)"
        },
        'Оператор беспилотных авиационных систем (с максимальной взлетной массой 30 килограммов и менее)': {
            1: "Правовое регулирование использования БАС",
            2: "Введение в БАС. БАС в правовом поле(Аттестация)",
            3: "Правовое регулирование",
            4: "Обслуживание и ремонт БАС(Аттестация)",
            5: "Составные части БПЛА",
            6: "Основы управления и пилотрования БАС"
        },
        'Специалист по борьбе с беспилотными летательными аппаратами и защите объектов':{
            1: "Введение в БАС. БАС в правовом поле",
            2: "Связь и навигация",
            3: "Основы радиоэлектронной борьбы (РЭБ)",
            4: "Подготовка и применение средств радиоэлектронной борьбы"
        }
    }
    context = {}
    result = {}
    if request.method == 'POST':
        form = AtlasLeadImportForm(request.POST, request.FILES)
        if form.is_valid():
            failed_to_find = 0
            file = form.cleaned_data['excel_file']
        
            # Читаем Excel с пропуском первых 2 строк (номеруем с 0)
            df = pd.read_excel(file, header=None, engine='openpyxl')
            amount_of_leads = 0
            for _, row in df.iterrows():
                if _ < 2:  # пропускаем первые 3 строки
                    continue
                name = row.iloc[1]
                program = row.iloc[0]
                email = row.iloc[2]
                last_active = row.iloc[5]
                potok = row.iloc[7]
                col_index = 11
                test_count = 0
                progress = ''
                razdel = 1
                while col_index + 4 < len(row):
                    topic_theory = row.iloc[col_index]       # теория (не нужна)
                    topic_testing = row.iloc[col_index + 1]  # тестирование (надо)
                    topic_practice = row.iloc[col_index + 2] # практика (не нужна)
                    topic_start = row.iloc[col_index + 3]    # дата старта (не нужна)
                    topic_end = row.iloc[col_index + 4]      # дата окончания (не нужна)
                    if pd.notna(topic_testing) and str(topic_testing).strip() != '':
                        progress += f"{topic_testing},"
                        if topic_testing > 60:
                            test_count +=1
                        razdel +=1
                    
                    col_index += 5
                progress += f"{test_count}"

                if isinstance(last_active, str):
                    last_active = datetime.strptime(last_active, "%d.%m.%Y")
                elif isinstance(last_active, pd.Timestamp):
                    last_active = last_active.to_pydatetime()
                # Пытаемся найти пользователя по email

# for program_id, program_name in EDUCATION_PROGRAMM:
                #     if program_name == program:
                #         program = program_id
                if isinstance(last_active, str):
                    dt = datetime.strptime(last_active, "%d.%m.%Y")
                    last_active = timezone.make_aware(dt, timezone.get_current_timezone())
                try:
                    app = AtlasApplication.objects.filter(email=email).first()
                    app.program = program
                    app.potok = potok
                    app.last_active = last_active
                    app.education_progress = progress
                    app.save()
                    amount_of_leads += 1
                except:
                    failed_to_find +=1
                    pass
            
            messages.success(request, f'Найдено: {amount_of_leads}')
                            
    
    else:
        form = AtlasLeadImportForm()
        context = {
            'form': form
        }
    applications = AtlasApplication.objects.all()

    selected_program = request.GET.get('program', '')
    selected_potok = request.GET.get('potok', '')

    if selected_program:
        applications = applications.filter(program=selected_program)
    if selected_potok:
        applications = applications.filter(potok=selected_potok)

    all_programs = sorted(set(app.program for app in AtlasApplication.objects.all() if app.program))
    all_potoks = sorted(set(app.potok for app in AtlasApplication.objects.all() if app.potok and app.potok != "nan"))

    # try:
    for app in applications:
        index = 0
        try:
            program = app.program
            if program in education_products:
                potok = app.potok
                if potok == "nan":
                    try:
                        start = app.raw_data.get("Начало периода обучения")
                        end = app.raw_data.get("Окончание периода обучения")
                        if start != None and end != None:
                            potok = f"{start}-{end}"
                        else:
                            potok = "Поток неопределен"
                    except:
                        potok = "Поток неопределен"
                full_name = app.full_name
                education_progress = app.education_progress
                result.setdefault(program, {})
                result[program].setdefault(potok, {})
                result[program][potok].setdefault('total', {topic: 0 for topic in education_products[program].values()})
                result[program][potok]['total'].setdefault('total', 0)
                result[program][potok]['total'].setdefault('undone', 0)
                result[program][potok].setdefault(full_name, {topic:0 for topic in education_products[program].values()})
                result[program][potok][full_name].setdefault('total', 0)
                result[program][potok][full_name].setdefault('email', app.email)
                result[program][potok][full_name].setdefault('phone', app.phone)
                
                if program not in result:
                    result[program] = {}
                if potok not in result[program]:
                    result[program][potok] = {}
                prog = education_progress.split(",")
                for topic in education_products[program].values():
                    result[program][potok][full_name][topic] = int(prog[index])
                    if (prog[index] == '0'):
                        result[program][potok]['total'][topic] += 1
                    index += 1
                result[program][potok][full_name]['total'] = int(prog[index])
                if (int(prog[index]) < len(education_products[program].values())):
                    result[program][potok]['total']['undone'] += 1
                result[program][potok]['total']['total'] += 1
        except Exception as e:
            print(f"Ошибка при формировании таблицы: {e}")
            pass
    context = {
    'result': result,
    'topics': education_products,
    'form': form,
    'all_programs': all_programs,
    'all_potoks': all_potoks,
    'selected_program': selected_program,
    'selected_potok': selected_potok
    }
    # return JsonResponse({'result': result})
    return render(request, 'crm_connector/attestation-progress.html', context)