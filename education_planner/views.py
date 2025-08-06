from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Sum, Prefetch
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import transaction
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .forms import EducationProgramForm, ProgramSectionFormSet
from .models import (
    EducationProgram, EduAgreement, Quota, Supplement, QuotaChange, Region
)
import json
import pandas as pd
import re
import io
import os

# Create your views here.

def clean_text_data(text):
    """Очистка текстовых данных от лишних символов"""
    if not text or pd.isna(text):
        return ""
    
    text = str(text).strip()
    # Убираем переводы строк и табуляции
    text = re.sub(r'[\n\r\t]+', ' ', text)
    # Убираем множественные пробелы
    text = re.sub(r'\s+', ' ', text)
    # Убираем пробелы в начале и конце
    text = text.strip()
    
    return text


def find_region_without_creating(region_name_input):
    """Поиск региона по названию БЕЗ автоматического создания"""
    region_name = clean_text_data(region_name_input)
    
    if not region_name:
        return None, 'empty_name'
    
    # Сначала точный поиск
    region = Region.objects.filter(name__iexact=region_name).first()
    if region:
        return region, 'exact_match'
    
    # Поиск по частичному совпадению
    region = Region.objects.filter(name__icontains=region_name).first()
    if region:
        return region, 'partial_match'
    
    # Поиск в обратную сторону (может регион содержит введенное название)
    region = Region.objects.filter(name__icontains=region_name.split()[0] if region_name.split() else region_name).first()
    if region:
        return region, 'reverse_match'
    
    # Если не найден, пытаемся определить по ключевым словам
    region_mapping = {
        'москва': 'Москва',
        'московская': 'Московская область',
        'спб': 'Санкт-Петербург',
        'санкт-петербург': 'Санкт-Петербург',
        'ленинградская': 'Ленинградская область',
        'екатеринбург': 'Свердловская область',
        'новосибирск': 'Новосибирская область',
        'казань': 'Республика Татарстан',
        'нижний новгород': 'Нижегородская область',
        'челябинск': 'Челябинская область',
        'омск': 'Омская область',
        'самара': 'Самарская область',
        'ростов': 'Ростовская область',
        'уфа': 'Республика Башкортостан',
        'красноярск': 'Красноярский край',
        'воронеж': 'Воронежская область',
        'пермь': 'Пермский край',
        'волгоград': 'Волгоградская область',
    }
    
    region_lower = region_name.lower()
    for key, standard_name in region_mapping.items():
        if key in region_lower:
            # Ищем стандартное название
            region = Region.objects.filter(name__icontains=standard_name).first()
            if region:
                return region, 'keyword_match'
    
    # Если ничего не подошло, возвращаем None с типом ошибки
    return None, 'not_found'


def find_or_create_region(region_name_input):
    """Поиск региона по названию или создание псевдонима (старая функция для совместимости)"""
    region_name = clean_text_data(region_name_input)
    
    if not region_name:
        return None, f'Пустое название региона'
    
    # Сначала точный поиск
    region = Region.objects.filter(name__iexact=region_name).first()
    if region:
        return region, None
    
    # Поиск по частичному совпадению
    region = Region.objects.filter(name__icontains=region_name).first()
    if region:
        return region, None
    
    # Поиск в обратную сторону (может регион содержит введенное название)
    region = Region.objects.filter(name__icontains=region_name.split()[0] if region_name.split() else region_name).first()
    if region:
        return region, None
    
    # Если не найден, пытаемся определить по ключевым словам
    region_mapping = {
        'москва': 'Москва',
        'московская': 'Московская область',
        'спб': 'Санкт-Петербург',
        'санкт-петербург': 'Санкт-Петербург',
        'ленинградская': 'Ленинградская область',
        'екатеринбург': 'Свердловская область',
        'новосибирск': 'Новосибирская область',
        'казань': 'Республика Татарстан',
        'нижний новгород': 'Нижегородская область',
        'челябинск': 'Челябинская область',
        'омск': 'Омская область',
        'самара': 'Самарская область',
        'ростов': 'Ростовская область',
        'уфа': 'Республика Башкортостан',
        'красноярск': 'Красноярский край',
        'воронеж': 'Воронежская область',
        'пермь': 'Пермский край',
        'волгоград': 'Волгоградская область',
    }
    
    region_lower = region_name.lower()
    for key, standard_name in region_mapping.items():
        if key in region_lower:
            # Ищем стандартное название
            region = Region.objects.filter(name__icontains=standard_name).first()
            if region:
                return region, None
            # Если стандартного тоже нет, создаем новый
            region = Region.objects.create(
                name=standard_name,
                code=standard_name[:10].upper().replace(' ', '_'),
                is_active=True
            )
            return region, f'Создан регион "{standard_name}" на основе "{region_name}"'
    
    # Если ничего не подошло, создаем новый регион
    try:
        region = Region.objects.create(
            name=region_name,
            code=region_name[:10].upper().replace(' ', '_').replace('-', '_'),
            is_active=True
        )
        return region, f'Создан новый регион "{region_name}"'
    except Exception as e:
        return None, f'Ошибка создания региона "{region_name}": {str(e)}'

@login_required
def program_list(request):
    programs = EducationProgram.objects.all()
    return render(request, 'education_planner/program_list.html', {'programs': programs})

@login_required
def create_program(request):
    if request.method == 'POST':
        program_form = EducationProgramForm(request.POST)
        section_formset = ProgramSectionFormSet(request.POST)
        
        if program_form.is_valid() and section_formset.is_valid():
            program = program_form.save()
            sections = section_formset.save(commit=False)
            total_workload = 0
            for section in sections:
                section.program = program
                section.workload = (section.lecture_hours or 0) + (section.practice_hours or 0) + (section.selfstudy_hours or 0)
                total_workload += section.workload
                section.save()
            program.academic_hours = total_workload + (program.final_attestation or 0)
            program.save()
            messages.success(request, 'Программа успешно создана!')
            return redirect('education_planner:program_list')
    else:
        program_form = EducationProgramForm()
        section_formset = ProgramSectionFormSet()

    context = {
        'program_form': program_form,
        'section_formset': section_formset,
    }
    return render(request, 'education_planner/create_program.html', context)


@login_required
def agreements_dashboard(request):
    """Главная страница управления договорами"""
    # Получаем параметры фильтрации
    search_query = request.GET.get('search', '')
    federal_operator = request.GET.get('operator', '')
    status = request.GET.get('status', '')
    
    # Базовый queryset с предзагрузкой связанных данных
    agreements = EduAgreement.objects.prefetch_related(
        Prefetch('quotas', queryset=Quota.objects.filter(is_active=True).select_related('education_program')),
        Prefetch('supplements', queryset=Supplement.objects.order_by('-signing_date'))
    ).select_related()
    
    # Применяем фильтры
    if search_query:
        agreements = agreements.filter(
            Q(number__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(notes__icontains=search_query)
        )
    
    if federal_operator:
        agreements = agreements.filter(federal_operator=federal_operator)
    
    if status:
        agreements = agreements.filter(status=status)
    
    # Сортировка
    agreements = agreements.order_by('-signing_date', '-created_at')
    
    # Пагинация
    paginator = Paginator(agreements, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Получаем все программы для выпадающего списка
    programs = EducationProgram.objects.all().order_by('name')
    
    # Группируем программы по названию для удобного выбора
    programs_grouped = {}
    for program in programs:
        if program.name not in programs_grouped:
            programs_grouped[program.name] = []
        programs_grouped[program.name].append({
            'id': program.id,
            'duration': program.academic_hours,
            'form': program.get_study_form_display(),
            'form_code': program.study_form,
            'type': program.get_program_type_display()
        })
    
    # Получаем уникальные названия программ
    unique_program_names = sorted(programs_grouped.keys())
    
    # Получаем все активные регионы
    regions = Region.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'agreements': page_obj.object_list,
        'all_agreements': agreements,  # Для статистики нужны все, не только на странице
        'programs': programs,
        'programs_grouped': json.dumps(programs_grouped, ensure_ascii=False),
        'unique_program_names': unique_program_names,
        'regions': regions,
        'search_query': search_query,
        'selected_operator': federal_operator,
        'selected_status': status,
        'operators': EduAgreement.FederalOperator.choices,
        'statuses': EduAgreement.AgreementStatus.choices,
        'status_choices': EduAgreement.AgreementStatus.choices,
    }
    
    return render(request, 'education_planner/agreements_dashboard.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def agreement_detail(request, pk):
    """Детальная информация о договоре с возможностью редактирования"""
    agreement = get_object_or_404(EduAgreement, pk=pk)
    
    if request.method == 'POST':
        # Обработка AJAX запроса на обновление
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                data = json.loads(request.body)
                
                # Обновляем поля договора
                agreement.name = data.get('name', agreement.name)
                agreement.number = data.get('number', agreement.number)
                agreement.federal_operator = data.get('federal_operator', agreement.federal_operator)
                agreement.status = data.get('status', agreement.status)
                agreement.document_link = data.get('document_link', agreement.document_link)
                agreement.notes = data.get('notes', agreement.notes)
                
                if data.get('signing_date'):
                    agreement.signing_date = data.get('signing_date')
                
                agreement.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Договор успешно обновлен'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                }, status=400)
    
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Возвращаем JSON данные для AJAX запроса (для редактирования)
        return JsonResponse({
            'id': agreement.id,
            'name': agreement.name,
            'number': agreement.number,
            'federal_operator': agreement.federal_operator,
            'status': agreement.status,
            'signing_date': agreement.signing_date.strftime('%Y-%m-%d') if agreement.signing_date else '',
            'document_link': agreement.document_link,
            'notes': agreement.notes
        })
    
    # Получаем актуальные квоты с учетом допсоглашений
    actual_quotas = agreement.get_actual_quotas()
    
    # Получаем все допсоглашения
    supplements = agreement.supplements.prefetch_related(
        Prefetch('quota_changes', queryset=QuotaChange.objects.select_related('education_program'))
    ).order_by('-signing_date')
    
    context = {
        'agreement': agreement,
        'actual_quotas': actual_quotas,
        'supplements': supplements,
        'operators': EduAgreement.FederalOperator.choices,
        'statuses': EduAgreement.AgreementStatus.choices,
    }
    
    return render(request, 'education_planner/agreement_detail.html', context)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def create_agreement(request):
    """Создание нового договора через AJAX"""
    try:
        data = json.loads(request.body)
        
        # Создаем новый договор
        agreement = EduAgreement.objects.create(
            federal_operator=data.get('federal_operator', 'IRPO'),
            name=data['name'],
            number=data['number'],
            signing_date=data.get('signing_date') if data.get('signing_date') else None,
            status=data.get('status', 'NEGOTIATION'),
            document_link=data.get('document_link', ''),
            notes=data.get('notes', '')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Договор успешно создан',
            'agreement_id': agreement.id
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def delete_agreement(request, pk):
    """Удаление договора через AJAX"""
    try:
        agreement = get_object_or_404(EduAgreement, pk=pk)
        agreement.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Договор успешно удален'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def manage_quota(request, agreement_id):
    """Управление квотами договора через AJAX"""
    agreement = get_object_or_404(EduAgreement, pk=agreement_id)
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        if action == 'create':
            # Создание новой квоты
            from datetime import datetime
            
            # Обработка дат
            start_date = None
            end_date = None
            if data.get('start_date'):
                try:
                    start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
                except ValueError:
                    pass
            if data.get('end_date'):
                try:
                    end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            quota = Quota.objects.create(
                agreement=agreement,
                education_program_id=data['program_id'],
                quantity=data['quantity'],
                cost_per_quota=data.get('cost_per_quota', 0),
                start_date=start_date,
                end_date=end_date
            )
            # Добавляем выбранные регионы
            region_ids = data.get('regions', [])
            if region_ids:
                quota.regions.set(region_ids)
            
            return JsonResponse({
                'success': True,
                'message': 'Квота успешно добавлена',
                'quota_id': quota.id
            })
            
        elif action == 'update':
            # Обновление существующей квоты
            from datetime import datetime
            
            quota = get_object_or_404(Quota, pk=data['quota_id'], agreement=agreement)
            quota.quantity = data['quantity']
            quota.cost_per_quota = data.get('cost_per_quota', quota.cost_per_quota)
            
            # Обработка дат
            if 'start_date' in data:
                if data['start_date']:
                    try:
                        quota.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
                    except ValueError:
                        pass
                else:
                    quota.start_date = None
                    
            if 'end_date' in data:
                if data['end_date']:
                    try:
                        quota.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
                    except ValueError:
                        pass
                else:
                    quota.end_date = None
            
            quota.save()
            
            # Обновляем регионы если они переданы
            region_ids = data.get('regions', [])
            if region_ids:
                quota.regions.set(region_ids)
            
            return JsonResponse({
                'success': True,
                'message': 'Квота успешно обновлена'
            })
            
        elif action == 'delete':
            # Удаление квоты
            quota = get_object_or_404(Quota, pk=data['quota_id'], agreement=agreement)
            quota.is_active = False
            quota.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Квота успешно удалена'
            })
            
        else:
            return JsonResponse({
                'success': False,
                'message': 'Неизвестное действие'
            }, status=400)
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def create_supplement(request, agreement_id):
    """Создание дополнительного соглашения через AJAX"""
    agreement = get_object_or_404(EduAgreement, pk=agreement_id)
    
    try:
        data = json.loads(request.body)
        
        # Создаем допсоглашение
        supplement = Supplement.objects.create(
            agreement=agreement,
            number=data['number'],
            signing_date=data.get('signing_date') if data.get('signing_date') else None,
            description=data['description'],
            status=data.get('status', 'DRAFT'),
            document_link=data.get('document_link', '')
        )
        
        # Создаем изменения квот
        for change_data in data.get('quota_changes', []):
            QuotaChange.objects.create(
                supplement=supplement,
                change_type=change_data['change_type'],
                education_program_id=change_data['program_id'],
                region=change_data['region'],
                old_quantity=change_data.get('old_quantity'),
                new_quantity=change_data['new_quantity'],
                comment=change_data.get('comment', '')
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Дополнительное соглашение успешно создано',
            'supplement_id': supplement.id
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
def supplement_detail(request, pk):
    """Детальная информация о дополнительном соглашении (для модального окна)"""
    supplement = get_object_or_404(Supplement, pk=pk)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Возвращаем JSON для AJAX запроса
        changes = []
        for change in supplement.quota_changes.select_related('education_program'):
            changes.append({
                'type': change.get_change_type_display(),
                'program': change.education_program.name,
                'region': change.region,
                'old_quantity': change.old_quantity,
                'new_quantity': change.new_quantity,
                'comment': change.comment
            })
        
        return JsonResponse({
            'number': supplement.number,
            'signing_date': supplement.signing_date.strftime('%d.%m.%Y') if supplement.signing_date else 'Не подписано',
            'status': supplement.get_status_display(),
            'description': supplement.description,
            'document_link': supplement.document_link,
            'changes': changes
        })
    
    # Для обычного запроса возвращаем HTML
    context = {
        'supplement': supplement,
        'changes': supplement.quota_changes.select_related('education_program')
    }
    
    return render(request, 'education_planner/supplement_detail.html', context)


@login_required
@require_http_methods(["GET"])
def quota_detail(request, quota_id):
    """Получение деталей квоты для редактирования"""
    quota = get_object_or_404(Quota, pk=quota_id)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Возвращаем JSON для AJAX запроса
        region_ids = list(quota.regions.values_list('id', flat=True))
        
        return JsonResponse({
            'success': True,
            'quota': {
                'id': quota.id,
                'quantity': quota.quantity,
                'cost_per_quota': float(quota.cost_per_quota),
                'region_ids': region_ids,
                'agreement_id': quota.agreement.id,
                'start_date': quota.start_date.strftime('%Y-%m-%d') if quota.start_date else '',
                'end_date': quota.end_date.strftime('%Y-%m-%d') if quota.end_date else '',
                'education_program': {
                    'id': quota.education_program.id,
                    'name': quota.education_program.name,
                    'academic_hours': quota.education_program.academic_hours,
                    'study_form': quota.education_program.get_study_form_display()
                }
            }
        })
    
    # Для обычного запроса можно вернуть HTML или редирект
    return JsonResponse({'success': False, 'message': 'Метод не поддерживается'})


@login_required
@require_http_methods(["POST"])
def analyze_quotas_excel(request):
    """Предварительный анализ Excel файла для выявления неопознанных регионов"""
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    import pandas as pd
    from datetime import datetime
    import os
    
    if not request.FILES.get('excel_file'):
        return JsonResponse({'success': False, 'message': 'Файл не выбран'})
    
    excel_file = request.FILES['excel_file']
    
    # Проверяем расширение файла
    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'message': 'Поддерживаются только файлы Excel (.xlsx, .xls)'})
    
    try:
        # Сохраняем временный файл
        file_name = f'temp_analyze_{timezone.now().timestamp()}_{excel_file.name}'
        file_path = default_storage.save(file_name, ContentFile(excel_file.read()))
        full_path = default_storage.path(file_path)
        
        # Читаем Excel файл
        df = pd.read_excel(full_path)
        
        # Проверяем необходимые колонки
        required_columns = [
            'договор_номер', 'программа_название', 'программа_тип', 'программа_часы', 
            'программа_форма', 'регионы', 'количество', 'стоимость_за_заявку'
        ]
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            # Удаляем временный файл
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
            return JsonResponse({
                'success': False, 
                'message': f'Отсутствуют необходимые колонки: {", ".join(missing_columns)}'
            })
        
        # Анализируем регионы
        unrecognized_regions = []
        region_suggestions = {}
        total_rows = 0
        
        for index, row in df.iterrows():
            total_rows += 1
            try:
                regions_text = clean_text_data(row['регионы'])
                if not regions_text:
                    continue
                    
                regions_names = [clean_text_data(name) for name in regions_text.split(',') if clean_text_data(name)]
                
                for region_name in regions_names:
                    region, match_type = find_region_without_creating(region_name)
                    
                    if match_type == 'not_found':
                        if region_name not in [ur['original'] for ur in unrecognized_regions]:
                            # Ищем возможные совпадения для предложений
                            suggestions = Region.objects.filter(
                                name__icontains=region_name[:3] if len(region_name) > 3 else region_name
                            )[:5]
                            
                            unrecognized_regions.append({
                                'original': region_name,
                                'suggestions': [{'id': r.id, 'name': r.name} for r in suggestions]
                            })
                            
            except Exception as e:
                continue
        
        # Удаляем временный файл
        if default_storage.exists(file_path):
            default_storage.delete(file_path)
        
        # Сохраняем данные файла в сессии для последующего импорта
        request.session['import_file_data'] = df.to_json()
        request.session['import_file_name'] = excel_file.name
        request.session.modified = True  # Принудительно сохраняем сессию
        
        return JsonResponse({
            'success': True,
            'total_rows': total_rows,
            'unrecognized_regions': unrecognized_regions,
            'needs_user_input': len(unrecognized_regions) > 0
        })
        
    except Exception as e:
        # Удаляем временный файл в случае ошибки
        if 'file_path' in locals() and default_storage.exists(file_path):
            default_storage.delete(file_path)
        return JsonResponse({'success': False, 'message': f'Ошибка анализа файла: {str(e)}'})


@login_required
@require_http_methods(["POST"])
def save_region_mappings(request):
    """Сохранение пользовательских выборов регионов"""
    try:
        data = json.loads(request.body)
        region_mappings = data.get('region_mappings', {})
        
        # Сохраняем маппинг в сессии
        request.session['region_mappings'] = region_mappings
        request.session.modified = True  # Принудительно сохраняем сессию
        
        return JsonResponse({'success': True, 'message': 'Настройки регионов сохранены'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка сохранения настроек: {str(e)}'})


def process_excel_import(df, file_name, region_mappings={}, use_old_region_logic=False):
    """Универсальная функция для обработки импорта Excel"""
    from datetime import datetime
    import pandas as pd
    
    # Проверяем необходимые колонки
    required_columns = [
        'договор_номер', 'программа_название', 'программа_тип', 'программа_часы', 
        'программа_форма', 'регионы', 'количество', 'стоимость_за_заявку'
    ]
    
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        return JsonResponse({
            'success': False, 
            'message': f'Отсутствуют обязательные колонки: {", ".join(missing_columns)}'
        })
    
    # Статистика
    created_count = 0
    error_count = 0
    errors = []
    
    with transaction.atomic():
        for index, row in df.iterrows():
            try:
                agreement_number = clean_text_data(row['договор_номер'])
                program_name = clean_text_data(row['программа_название'])
                program_type = clean_text_data(row['программа_тип'])
                program_form = clean_text_data(row['программа_форма'])
                regions_text = clean_text_data(row['регионы'])
                
                if not all([agreement_number, program_name, regions_text]):
                    errors.append(f'Строка {index + 2}: Отсутствуют обязательные данные')
                    error_count += 1
                    continue

                # Ищем договор
                agreement = EduAgreement.objects.filter(number=agreement_number).first()
                if not agreement:
                    errors.append(f'Строка {index + 2}: Договор {agreement_number} не найден')
                    error_count += 1
                    continue

                # Ищем или создаем программу
                program = EducationProgram.objects.filter(
                    name__icontains=program_name,
                    academic_hours=int(row['программа_часы'])
                ).first()
                
                if not program:
                    # Создаем программу автоматически
                    try:
                        # Определяем тип программы
                        program_type_choices = {
                            'дпо пк': EducationProgram.ProgramType.QUALIFICATION_UPGRADE,
                            'повышение квалификации': EducationProgram.ProgramType.QUALIFICATION_UPGRADE,
                            'профессиональная переподготовка': EducationProgram.ProgramType.PROFESSIONAL_RETRAINING,
                            'программы профессионального обучения': EducationProgram.ProgramType.PROFESSIONAL_TRAINING
                        }
                        
                        program_type_key = program_type.lower()
                        program_type_value = program_type_choices.get(program_type_key, EducationProgram.ProgramType.QUALIFICATION_UPGRADE)
                        
                        # Определяем форму обучения
                        study_form_choices = {
                            'очная': EducationProgram.StudyForm.FULL_TIME,
                            'заочная': EducationProgram.StudyForm.PART_TIME,
                            'очно-заочная': EducationProgram.StudyForm.MIXED
                        }
                        
                        study_form_key = program_form.lower()
                        study_form_value = study_form_choices.get(study_form_key, EducationProgram.StudyForm.FULL_TIME)
                        
                        program = EducationProgram.objects.create(
                            name=program_name,
                            program_type=program_type_value,
                            academic_hours=int(row['программа_часы']),
                            study_form=study_form_value,
                            description=f'Автоматически создана при импорте квот'
                        )
                        
                    except Exception as e:
                        errors.append(f'Строка {index + 2}: Ошибка создания программы "{program_name}" - {str(e)}')
                        error_count += 1
                        continue

                # Парсим регионы с улучшенной обработкой скобок
                regions_names = []
                for name in regions_text.split(','):
                    cleaned_name = clean_text_data(name)
                    if cleaned_name:
                        # Убираем содержимое в скобках и лишние пробелы
                        cleaned_name = re.sub(r'\([^)]*\)', '', cleaned_name).strip()
                        if cleaned_name:
                            regions_names.append(cleaned_name)
                
                regions = []
                
                for region_name in regions_names:
                    if use_old_region_logic:
                        # Старая логика с автоматическим созданием
                        region, message = find_or_create_region(region_name)
                        if region:
                            regions.append(region)
                        else:
                            errors.append(f'Строка {index + 2}: {message}')
                    else:
                        # Новая логика с пользовательскими выборами
                        region, match_type = find_region_without_creating(region_name)
                        
                        if region:
                            regions.append(region)
                        else:
                            # Если не найден, ищем в пользовательских выборах
                            if region_name in region_mappings:
                                mapping_info = region_mappings[region_name]
                                
                                if mapping_info['action'] == 'map':
                                    # Пользователь выбрал существующий регион
                                    mapped_region = Region.objects.filter(id=mapping_info['region_id']).first()
                                    if mapped_region:
                                        regions.append(mapped_region)
                                    else:
                                        errors.append(f'Строка {index + 2}: Выбранный регион (ID: {mapping_info["region_id"]}) не найден')
                                        
                                elif mapping_info['action'] == 'create':
                                    # Пользователь выбрал создать новый регион
                                    new_region_name = mapping_info['new_name']
                                    
                                    # Проверяем, не создан ли уже этот регион
                                    existing_region = Region.objects.filter(name=new_region_name).first()
                                    if existing_region:
                                        regions.append(existing_region)
                                    else:
                                        try:
                                            new_region = Region.objects.create(
                                                name=new_region_name,
                                                code=new_region_name[:10].upper().replace(' ', '_').replace('-', '_'),
                                                is_active=True
                                            )
                                            regions.append(new_region)
                                        except Exception as e:
                                            errors.append(f'Строка {index + 2}: Ошибка создания региона "{new_region_name}": {str(e)}')
                                            
                                elif mapping_info['action'] == 'skip':
                                    # Пользователь выбрал пропустить этот регион
                                    continue
                            else:
                                # Регион не найден и нет пользовательского выбора
                                errors.append(f'Строка {index + 2}: Регион "{region_name}" не найден и не настроен')
                
                if not regions:
                    error_count += 1
                    continue

                # Обрабатываем даты
                start_date = None
                end_date = None
                
                if 'дата_начала' in df.columns and pd.notna(row['дата_начала']):
                    try:
                        start_date = datetime.strptime(str(row['дата_начала']), '%d.%m.%Y').date()
                    except:
                        pass
                
                if 'дата_окончания' in df.columns and pd.notna(row['дата_окончания']):
                    try:
                        end_date = datetime.strptime(str(row['дата_окончания']), '%d.%m.%Y').date()
                    except:
                        pass

                # Создаем квоту
                quota = Quota.objects.create(
                    agreement=agreement,
                    education_program=program,
                    quantity=int(row['количество']),
                    cost_per_quota=float(row['стоимость_за_заявку']),
                    start_date=start_date,
                    end_date=end_date
                )
                
                # Устанавливаем регионы
                quota.regions.set(regions)
                
                created_count += 1
                
            except Exception as e:
                errors.append(f'Строка {index + 2}: Ошибка импорта - {str(e)}')
                error_count += 1

    # Возвращаем результат
    return JsonResponse({
        'success': True,
        'created_count': created_count,
        'error_count': error_count,
        'errors': errors[:10]  # Ограничиваем количество ошибок для отображения
    })


@login_required
@require_http_methods(["POST"])
def import_quotas_excel_direct(request):
    """Прямой импорт квот из Excel файла БЕЗ интерактивного анализа (для совместимости)"""
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    import pandas as pd
    from datetime import datetime
    import os
    
    if not request.FILES.get('excel_file'):
        return JsonResponse({'success': False, 'message': 'Файл не выбран'})
    
    excel_file = request.FILES['excel_file']
    
    # Проверяем расширение файла
    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'message': 'Поддерживаются только файлы Excel (.xlsx, .xls)'})
    
    try:
        # Сохраняем временный файл
        file_name = f'temp_direct_import_{timezone.now().timestamp()}_{excel_file.name}'
        file_path = default_storage.save(file_name, ContentFile(excel_file.read()))
        full_path = default_storage.path(file_path)
        
        # Читаем Excel файл
        df = pd.read_excel(full_path)
        
        # Удаляем временный файл
        if default_storage.exists(file_path):
            default_storage.delete(file_path)
        
        # Выполняем импорт с автоматическим созданием регионов (старая логика)
        return process_excel_import(df, excel_file.name, region_mappings={}, use_old_region_logic=True)
        
    except Exception as e:
        # Удаляем временный файл в случае ошибки
        if 'file_path' in locals() and default_storage.exists(file_path):
            default_storage.delete(file_path)
        return JsonResponse({'success': False, 'message': f'Ошибка импорта файла: {str(e)}'})


@login_required
@require_http_methods(["POST"])
def import_quotas_excel(request):
    """Финальный импорт квот из Excel файла с пользовательскими настройками регионов"""
    import pandas as pd
    from datetime import datetime
    import json
    
    try:
        # Получаем данные из сессии
        import_file_data = request.session.get('import_file_data')
        region_mappings = request.session.get('region_mappings', {})
        
        # Отладочная информация
        session_keys = list(request.session.keys())
        print(f"DEBUG: Ключи сессии: {session_keys}")
        print(f"DEBUG: Есть import_file_data: {import_file_data is not None}")
        print(f"DEBUG: Размер region_mappings: {len(region_mappings)}")
        
        if not import_file_data:
            return JsonResponse({
                'success': False, 
                'message': f'Данные файла не найдены. Ключи сессии: {session_keys}. Повторите анализ файла.'
            })
        
        # Восстанавливаем DataFrame из JSON
        df = pd.read_json(import_file_data)
        file_name = request.session.get('import_file_name', 'excel_file.xlsx')
        
        # Очищаем сессию
        del request.session['import_file_data']
        if 'region_mappings' in request.session:
            del request.session['region_mappings']
        if 'import_file_name' in request.session:
            del request.session['import_file_name']
        
        # Выполняем импорт с пользовательскими настройками
        return process_excel_import(df, file_name, region_mappings, use_old_region_logic=False)
        
        # Проверяем необходимые колонки
        required_columns = [
            'договор_номер', 'программа_название', 'программа_тип', 'программа_часы', 
            'программа_форма', 'регионы', 'количество', 'стоимость_за_заявку'
        ]
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return JsonResponse({
                'success': False, 
                'message': f'Отсутствуют обязательные колонки: {", ".join(missing_columns)}'
            })
        
        # Статистика
        created_count = 0
        error_count = 0
        errors = []
        
        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    # Очищаем текстовые данные
                    agreement_number = clean_text_data(row['договор_номер'])
                    program_name = clean_text_data(row['программа_название'])
                    program_type = clean_text_data(row['программа_тип'])
                    program_form = clean_text_data(row['программа_форма'])
                    regions_text = clean_text_data(row['регионы'])
                    
                    # Ищем договор
                    agreement = EduAgreement.objects.filter(
                        number=agreement_number
                    ).first()
                    
                    if not agreement:
                        errors.append(f'Строка {index + 2}: Договор {agreement_number} не найден')
                        error_count += 1
                        continue

                    # Ищем или создаем программу обучения
                    program = EducationProgram.objects.filter(
                        name__icontains=program_name,
                        academic_hours=int(row['программа_часы'])
                    ).first()
                    
                    if not program:
                        # Создаем программу автоматически
                        try:
                            # Определяем тип программы
                            program_type_choices = {
                                'повышение квалификации': EducationProgram.ProgramType.QUALIFICATION_UPGRADE,
                                'профессиональная переподготовка': EducationProgram.ProgramType.PROFESSIONAL_RETRAINING,
                                'программы профессионального обучения': EducationProgram.ProgramType.PROFESSIONAL_TRAINING
                            }
                            
                            program_type_key = program_type.lower()
                            program_type_value = program_type_choices.get(program_type_key, EducationProgram.ProgramType.QUALIFICATION_UPGRADE)
                            
                            # Определяем форму обучения
                            study_form_choices = {
                                'очная': EducationProgram.StudyForm.FULL_TIME,
                                'заочная': EducationProgram.StudyForm.PART_TIME,
                                'очно-заочная': EducationProgram.StudyForm.MIXED
                            }
                            
                            study_form_key = program_form.lower()
                            study_form_value = study_form_choices.get(study_form_key, EducationProgram.StudyForm.FULL_TIME)
                            
                            program = EducationProgram.objects.create(
                                name=program_name,
                                program_type=program_type_value,
                                academic_hours=int(row['программа_часы']),
                                study_form=study_form_value,
                                description=f'Автоматически создана при импорте квот'
                            )
                            
                        except Exception as e:
                            errors.append(f'Строка {index + 2}: Ошибка создания программы "{program_name}" - {str(e)}')
                            error_count += 1
                            continue

                    # Парсим регионы с использованием пользовательских выборов
                    regions_names = [clean_text_data(name) for name in regions_text.split(',') if clean_text_data(name)]
                    regions = []
                    
                    for region_name in regions_names:
                        # Сначала пытаемся найти регион стандартным способом
                        region, match_type = find_region_without_creating(region_name)
                        
                        if region:
                            regions.append(region)
                        else:
                            # Если не найден, ищем в пользовательских выборах
                            if region_name in region_mappings:
                                mapping_info = region_mappings[region_name]
                                
                                if mapping_info['action'] == 'map':
                                    # Пользователь выбрал существующий регион
                                    mapped_region = Region.objects.filter(id=mapping_info['region_id']).first()
                                    if mapped_region:
                                        regions.append(mapped_region)
                                    else:
                                        errors.append(f'Строка {index + 2}: Выбранный регион (ID: {mapping_info["region_id"]}) не найден')
                                        
                                elif mapping_info['action'] == 'create':
                                    # Пользователь выбрал создать новый регион
                                    new_region_name = mapping_info['new_name']
                                    
                                    # Проверяем, не создан ли уже этот регион
                                    existing_region = Region.objects.filter(name=new_region_name).first()
                                    if existing_region:
                                        regions.append(existing_region)
                                    else:
                                        try:
                                            new_region = Region.objects.create(
                                                name=new_region_name,
                                                code=new_region_name[:10].upper().replace(' ', '_').replace('-', '_'),
                                                is_active=True
                                            )
                                            regions.append(new_region)
                                        except Exception as e:
                                            errors.append(f'Строка {index + 2}: Ошибка создания региона "{new_region_name}": {str(e)}')
                                            
                                elif mapping_info['action'] == 'skip':
                                    # Пользователь выбрал пропустить этот регион
                                    continue
                            else:
                                # Регион не найден и нет пользовательского выбора
                                errors.append(f'Строка {index + 2}: Регион "{region_name}" не найден и не настроен')
                    
                    if not regions:
                        error_count += 1
                        continue

                    # Обрабатываем даты
                    start_date = None
                    end_date = None
                    
                    if 'дата_начала' in df.columns and pd.notna(row['дата_начала']):
                        try:
                            if isinstance(row['дата_начала'], str):
                                start_date = datetime.strptime(row['дата_начала'], '%d.%m.%Y').date()
                            else:
                                start_date = row['дата_начала'].date()
                        except (ValueError, AttributeError):
                            errors.append(f'Строка {index + 2}: Неверный формат даты начала')
                    
                    if 'дата_окончания' in df.columns and pd.notna(row['дата_окончания']):
                        try:
                            if isinstance(row['дата_окончания'], str):
                                end_date = datetime.strptime(row['дата_окончания'], '%d.%m.%Y').date()
                            else:
                                end_date = row['дата_окончания'].date()
                        except (ValueError, AttributeError):
                            errors.append(f'Строка {index + 2}: Неверный формат даты окончания')

                    # Валидация дат
                    if start_date and end_date and start_date > end_date:
                        errors.append(f'Строка {index + 2}: Дата начала не может быть позже даты окончания')
                        error_count += 1
                        continue

                    # Создаем квоту
                    quota = Quota.objects.create(
                        agreement=agreement,
                        education_program=program,
                        quantity=int(row['количество']),
                        cost_per_quota=float(row['стоимость_за_заявку']),
                        start_date=start_date,
                        end_date=end_date
                    )
                    quota.regions.set(regions)
                    created_count += 1

                except Exception as e:
                    errors.append(f'Строка {index + 2}: Ошибка импорта - {str(e)}')
                    error_count += 1
        
        # Удаляем временный файл
        if os.path.exists(full_path):
            os.remove(full_path)
        
        return JsonResponse({
            'success': True,
            'message': f'Импорт завершен! Создано квот: {created_count}',
            'created_count': created_count,
            'error_count': error_count,
            'errors': errors[:10]  # Ограничиваем количество ошибок для отображения
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': f'Ошибка при обработке файла: {str(e)}'
        })


@login_required
def download_quota_template(request):
    """Скачивание шаблона Excel для импорта квот"""
    import pandas as pd
    from django.http import HttpResponse
    import io
    
    # Создаем образец данных
    sample_data = {
        'договор_номер': ['ДОГ-001', 'ДОГ-002'],
        'программа_название': ['Основы искусственного интеллекта', 'Специалист по борьбе с беспилотными летательными аппаратами'],
        'программа_тип': ['Повышение квалификации', 'Профессиональная переподготовка'],
        'программа_часы': [144, 72],
        'программа_форма': ['Очная', 'Заочная'],
        'регионы': ['Москва, Московская область', 'Санкт-Петербург'],
        'количество': [25, 15],
        'стоимость_за_заявку': [50000.00, 35000.00],
        'дата_начала': ['01.09.2024', '15.10.2024'],
        'дата_окончания': ['15.12.2024', '30.11.2024']
    }
    
    df = pd.DataFrame(sample_data)
    
    # Создаем Excel файл в памяти
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Основные данные
        df.to_excel(writer, sheet_name='Квоты', index=False)
        
        # Инструкции на отдельном листе
        instructions = pd.DataFrame({
            'Колонка': [
                'договор_номер', 'программа_название', 'программа_тип', 'программа_часы', 'программа_форма',
                'регионы', 'количество', 'стоимость_за_заявку', 'дата_начала', 'дата_окончания'
            ],
            'Описание': [
                'Номер договора (должен существовать в системе)',
                'Название программы обучения (создается автоматически если не существует)',
                'Тип программы: Повышение квалификации, Профессиональная переподготовка, Программы профессионального обучения',
                'Количество академических часов программы',
                'Форма обучения (Очная/Заочная/Очно-заочная)',
                'Регионы через запятую (добавляются как псевдонимы если не найдены)',
                'Количество мест по квоте (целое число)',
                'Стоимость обучения одного человека (число с точкой)',
                'Дата начала обучения в формате ДД.ММ.ГГГГ (необязательно)',
                'Дата окончания обучения в формате ДД.ММ.ГГГГ (необязательно)'
            ],
            'Обязательность': [
                'Обязательно', 'Обязательно', 'Обязательно', 'Обязательно', 'Обязательно',
                'Обязательно', 'Обязательно', 'Обязательно', 'Необязательно', 'Необязательно'
            ]
        })
        instructions.to_excel(writer, sheet_name='Инструкция', index=False)
    
    output.seek(0)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="template_import_quotas.xlsx"'
    
    return response





@login_required
@csrf_exempt
@require_http_methods(["POST"])
def analyze_supplement_excel(request):
    """
    Анализирует Excel файл дополнительного соглашения
    """
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'success': False, 'message': 'Файл не найден'})
        
        file = request.FILES['file']
        agreement_id = request.POST.get('agreement_id')
        
        if not agreement_id:
            return JsonResponse({'success': False, 'message': 'ID договора не указан'})
        
        try:
            agreement = EduAgreement.objects.get(id=agreement_id)
        except EduAgreement.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Договор не найден'})
        
        # Читаем Excel файл
        try:
            df = pd.read_excel(file, engine='openpyxl')
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Ошибка чтения файла: {str(e)}'})
        
        # Проверяем наличие необходимых колонок
        required_columns = ['Программа обучения', 'Форма обучения', 'Длительность', 'Регионы реализации', 'Количество мест']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return JsonResponse({
                'success': False,
                'message': f'Отсутствуют обязательные колонки: {", ".join(missing_columns)}'
            })
        
        # Очищаем и парсим данные
        new_quotas = []
        unrecognized_regions = set()
        
        for index, row in df.iterrows():
            if pd.isna(row['Программа обучения']) or pd.isna(row['Количество мест']) or pd.isna(row['Длительность']):
                continue
            
            program_name = clean_text_data(str(row['Программа обучения']))
            program_type = clean_text_data(str(row.get('Форма обучения', '')))
            duration_text = clean_text_data(str(row.get('Длительность', '')))
            regions_text = clean_text_data(str(row['Регионы реализации']))
            
            try:
                quantity = int(row['Количество мест'])
            except (ValueError, TypeError):
                continue
            
            # Парсим длительность (академические часы)
            duration = None
            if duration_text:
                try:
                    # Извлекаем число из строки (например, "72 ч." -> 72)
                    import re
                    duration_match = re.search(r'(\d+)', duration_text)
                    if duration_match:
                        duration = int(duration_match.group(1))
                except (ValueError, TypeError):
                    pass
            
            if quantity <= 0:
                continue
            
            # Валидация длительности
            if not duration:
                continue  # Пропускаем строки без корректной длительности
            
            # Ищем программу
            program = None
            programs = EducationProgram.objects.filter(name__icontains=program_name)
            
            # Фильтруем по типу программы
            if program_type:
                for pt_choice, pt_display in EducationProgram.ProgramType.choices:
                    if program_type.lower() in pt_display.lower():
                        programs = programs.filter(program_type=pt_choice)
                        break
            
            # Фильтруем по длительности
            if duration:
                programs = programs.filter(academic_hours=duration)
            
            if programs.exists():
                program = programs.first()
            else:
                error_parts = [program_name]
                if program_type:
                    error_parts.append(f"тип: {program_type}")
                if duration:
                    error_parts.append(f"длительность: {duration} ч.")
                
                return JsonResponse({
                    'success': False,
                    'message': f'Программа не найдена: {" | ".join(error_parts)}'
                })
            
            # Парсим регионы
            regions_names = []
            for name in regions_text.split(','):
                cleaned_name = clean_text_data(name)
                if cleaned_name:
                    # Убираем содержимое в скобках
                    cleaned_name = re.sub(r'\([^)]*\)', '', cleaned_name).strip()
                    if cleaned_name:
                        regions_names.append(cleaned_name)
            
            # Проверяем регионы
            valid_regions = []
            for region_name in regions_names:
                region, match_type = find_region_without_creating(region_name)
                if match_type != 'not_found' and region:
                    valid_regions.append(region.name)
                else:
                    unrecognized_regions.add(region_name)
            
            if valid_regions:
                new_quotas.append({
                    'program_id': program.id,
                    'program_name': program.name,
                    'regions': valid_regions,
                    'quantity': quantity
                })
        
        # Сохраняем данные в сессии
        request.session['supplement_file_data'] = {
            'agreement_id': agreement_id,
            'new_quotas': new_quotas
        }
        request.session['supplement_file_name'] = file.name
        request.session['supplement_df_data'] = df.to_json()
        request.session.modified = True
        
        # Подготавливаем ответ
        response_data = {
            'success': True,
            'total_rows': len(df),
            'valid_quotas': len(new_quotas),
            'needs_user_input': len(unrecognized_regions) > 0,
            'unrecognized_regions': []
        }
        
        # Добавляем неопознанные регионы с предложениями
        if unrecognized_regions:
            for region_name in unrecognized_regions:
                # Ищем похожие регионы для предложений
                suggestions = Region.objects.filter(
                    name__icontains=region_name[:3] if len(region_name) > 3 else region_name
                ).values_list('name', flat=True)[:5]
                
                response_data['unrecognized_regions'].append({
                    'name': region_name,
                    'suggestions': list(suggestions)
                })
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка обработки файла: {str(e)}'})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def import_supplement_excel(request):
    """
    Выполняет импорт дополнительного соглашения из Excel
    Заменяет все квоты договора на новые из файла
    """
    try:
        # Получаем данные из сессии
        if 'supplement_file_data' not in request.session:
            return JsonResponse({'success': False, 'message': 'Данные файла не найдены. Повторите анализ файла.'})
        
        file_data = request.session['supplement_file_data']
        file_name = request.session.get('supplement_file_name', 'unknown.xlsx')
        
        # Получаем mappings регионов, если есть
        region_mappings = request.session.get('supplement_region_mappings', {})
        
        # Получаем данные дополнительного соглашения
        supplement_number = request.POST.get('supplement_number', '')
        supplement_description = request.POST.get('supplement_description', '')
        
        if not supplement_number:
            return JsonResponse({'success': False, 'message': 'Номер дополнительного соглашения обязателен'})
        
        agreement_id = file_data['agreement_id']
        
        try:
            agreement = EduAgreement.objects.get(id=agreement_id)
        except EduAgreement.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Договор не найден'})
        
        # Читаем данные из сессии повторно
        df_data = request.session.get('supplement_df_data')
        if not df_data:
            return JsonResponse({'success': False, 'message': 'Данные Excel файла не найдены'})
        
        df = pd.read_json(df_data)
        created_quotas = []
        
        with transaction.atomic():
            # Создаем дополнительное соглашение
            supplement = Supplement.objects.create(
                agreement=agreement,
                number=supplement_number,
                description=supplement_description or f'Импорт из файла {file_name}',
                status=Supplement.SupplementStatus.NEGOTIATION
            )
            
            # 1. Деактивируем все старые квоты
            agreement.quotas.update(is_active=False)
            
            # 2. Создаем новые квоты из файла
            for _, row in df.iterrows():
                try:
                    program_name = clean_text_data(str(row['Программа обучения']))
                    program_type = clean_text_data(str(row.get('Форма обучения', '')))
                    duration_text = clean_text_data(str(row.get('Длительность', '')))
                    regions_text = clean_text_data(str(row['Регионы реализации']))
                    
                    # Парсим количество
                    try:
                        quantity = int(float(str(row['Количество мест']).replace(' ', '')))
                    except (ValueError, TypeError):
                        continue
                    
                    if quantity <= 0:
                        continue
                    
                    # Парсим длительность
                    duration = None
                    if duration_text:
                        try:
                            import re
                            duration_match = re.search(r'(\d+)', duration_text)
                            if duration_match:
                                duration = int(duration_match.group(1))
                        except (ValueError, TypeError):
                            pass
                    
                    if not duration:
                        continue
                    
                    # Находим программу
                    programs = EducationProgram.objects.filter(name__icontains=program_name)
                    
                    if program_type:
                        for pt_choice, pt_display in EducationProgram.ProgramType.choices:
                            if program_type.lower() in pt_display.lower():
                                programs = programs.filter(program_type=pt_choice)
                                break
                    
                    if duration:
                        programs = programs.filter(academic_hours=duration)
                    
                    if not programs.exists():
                        continue
                    
                    program = programs.first()
                    
                    # Парсим регионы
                    regions_names = [clean_text_data(name.strip()) for name in regions_text.split(',')]
                    regions_names = [name for name in regions_names if name]
                    
                    valid_regions = []
                    for region_name in regions_names:
                        # Применяем mapping если есть
                        if region_name in region_mappings:
                            mapping = region_mappings[region_name]
                            if mapping['action'] == 'map':
                                region_name = mapping['target_region']
                            elif mapping['action'] == 'skip':
                                continue
                        
                        try:
                            region = Region.objects.get(name=region_name)
                            valid_regions.append(region)
                        except Region.DoesNotExist:
                            continue
                    
                    if not valid_regions:
                        continue
                    
                    # Парсим даты
                    start_date = None
                    end_date = None
                    cost_per_quota = None
                    
                    # Дата начала
                    if 'Дата начала' in row and pd.notna(row['Дата начала']):
                        try:
                            start_date_str = str(row['Дата начала']).strip()
                            if start_date_str and start_date_str != 'nan':
                                # Пробуем разные форматы дат
                                for date_format in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
                                    try:
                                        start_date = datetime.strptime(start_date_str, date_format).date()
                                        break
                                    except ValueError:
                                        continue
                        except (ValueError, TypeError):
                            pass
                    
                    # Дата окончания
                    if 'Дата окончания' in row and pd.notna(row['Дата окончания']):
                        try:
                            end_date_str = str(row['Дата окончания']).strip()
                            if end_date_str and end_date_str != 'nan':
                                # Пробуем разные форматы дат
                                for date_format in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
                                    try:
                                        end_date = datetime.strptime(end_date_str, date_format).date()
                                        break
                                    except ValueError:
                                        continue
                        except (ValueError, TypeError):
                            pass
                    
                    # Стоимость за заявку
                    if 'Стоимость за заявку' in row and pd.notna(row['Стоимость за заявку']):
                        try:
                            cost_str = str(row['Стоимость за заявку']).replace(' ', '').replace(',', '.')
                            if cost_str and cost_str != 'nan':
                                cost_per_quota = float(cost_str)
                        except (ValueError, TypeError):
                            pass
                    
                    # Создаем новую квоту
                    quota = Quota.objects.create(
                        agreement=agreement,
                        education_program=program,
                        quantity=quantity,
                        start_date=start_date,
                        end_date=end_date,
                        cost_per_quota=cost_per_quota,
                        is_active=True
                    )
                    quota.regions.set(valid_regions)
                    created_quotas.append(quota)
                    
                except Exception as e:
                    continue
        
        # Очищаем сессию
        if 'supplement_file_data' in request.session:
            del request.session['supplement_file_data']
        if 'supplement_file_name' in request.session:
            del request.session['supplement_file_name']
        if 'supplement_region_mappings' in request.session:
            del request.session['supplement_region_mappings']
        if 'supplement_df_data' in request.session:
            del request.session['supplement_df_data']
        request.session.modified = True
        
        return JsonResponse({
            'success': True,
            'supplement_id': supplement.id,
            'supplement_number': supplement.number,
            'quotas_count': len(created_quotas),
            'message': f'Дополнительное соглашение №{supplement.number} успешно создано. Квоты договора заменены ({len(created_quotas)} новых квот)'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка импорта: {str(e)}'})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def save_supplement_region_mappings(request):
    """
    Сохраняет mappings регионов для импорта дополнительного соглашения
    """
    try:
        import json
        data = json.loads(request.body)
        mappings = data.get('mappings', {})
        
        # Сохраняем в сессии
        request.session['supplement_region_mappings'] = mappings
        request.session.modified = True
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка сохранения: {str(e)}'})


@login_required
def download_supplement_template(request):
    """
    Скачивает шаблон Excel для импорта дополнительных соглашений
    """
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Создаем основной шаблон
        template_data = {
            'Программа обучения': [
                'Повышение квалификации по программе "Основы цифровой экономики"',
                'Профессиональная переподготовка "Управление проектами"'
            ],
            'Форма обучения': [
                'Очно-заочная',
                'Заочная'
            ],
            'Длительность': [
                '72 ч.',
                '250 ч.'
            ],
            'Регионы реализации': [
                'Республика Татарстан, Пермский край',
                'Московская область'
            ],
            'Количество мест': [50, 30],
            'Дата начала': ['01.09.2024', '15.09.2024'],
            'Дата окончания': ['01.12.2024', '15.12.2024'],
            'Стоимость за заявку': [15000, 25000]
        }
        template = pd.DataFrame(template_data)
        template.to_excel(writer, sheet_name='Квоты', index=False)
        
        # Создаем лист с инструкциями
        instructions_data = {
            'Поле': [
                'Программа обучения',
                'Форма обучения', 
                'Длительность',
                'Регионы реализации',
                'Количество мест',
                'Дата начала',
                'Дата окончания',
                'Стоимость за заявку'
            ],
            'Описание': [
                'Название программы обучения (должна существовать в системе)',
                'Тип программы: Повышение квалификации, Профессиональная переподготовка, Курсы',
                'Длительность в академических часах (например: "72 ч." или просто "72")',
                'Список регионов через запятую. Регионы должны быть в системе.',
                'Целое число больше 0',
                'Дата в формате ДД.ММ.ГГГГ',
                'Дата в формате ДД.ММ.ГГГГ (не раньше даты начала)',
                'Стоимость в рублях (число)'
            ],
            'Обязательность': [
                'Обязательно',
                'Обязательно',
                'Обязательно',
                'Обязательно', 
                'Обязательно',
                'Необязательно',
                'Необязательно',
                'Необязательно'
            ]
        }
        instructions = pd.DataFrame(instructions_data)
        instructions.to_excel(writer, sheet_name='Инструкция', index=False)
    
    output.seek(0)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="template_import_supplement.xlsx"'
    
    return response
