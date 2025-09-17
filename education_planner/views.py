from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Sum, Prefetch
from django.db import models
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import transaction
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .forms import EducationProgramForm, ProgramSectionFormSet
from .models import (
    EducationProgram, EduAgreement, Quota, Supplement, QuotaChange, Region, ROIV,
    Demand, DemandHistory, QuotaDistribution, AlternativeQuota
)
from .cache_utils import cache_atlas_data, AtlasDataCache
import json
import pandas as pd
import re
import io


def get_missing_columns_message(missing_columns, is_supplement=False, federal_operator=None):
    """
    Генерирует детальное сообщение об отсутствующих колонках в Excel файле
    """
    if is_supplement:
        # Описания для дополнительных соглашений
        column_descriptions = {
            'Программа обучения': 'Название программы обучения',
            'Форма обучения': 'Форма обучения (очная, заочная, очно-заочная, дистанционная)',
            'Длительность': 'Академические часы (например: 72 ч.)',
            'Регионы реализации': 'Регионы реализации (названия регионов через запятую)',
            'Количество мест': 'Количество мест',
            'Стоимость за заявку': 'Стоимость за одну заявку',
            'Дата начала': 'Дата начала обучения (DD.MM.YYYY)',
            'Дата окончания': 'Дата окончания обучения (DD.MM.YYYY)'
        }
    else:
        # Описания для основных договоров
        column_descriptions = {
            'договор_номер': 'Номер договора',
            'программа_название': 'Название программы обучения',
            'программа_тип': 'Тип программы (Повышение квалификации, Профессиональная переподготовка)',
            'программа_часы': 'Академические часы',
            'программа_форма': 'Форма обучения (очная, заочная, очно-заочная, дистанционная)',
            'регионы': 'Регионы реализации (названия регионов через запятую)',
            'количество': 'Количество мест',
            'стоимость_за_заявку': 'Стоимость за одну заявку',
            'дата_начала': 'Дата начала обучения (DD.MM.YYYY)',
            'дата_окончания': 'Дата окончания обучения (DD.MM.YYYY)'
        }
    
    missing_details = []
    for col in missing_columns:
        description = column_descriptions.get(col, col)
        missing_details.append(f"'{col}' ({description})")
    
    message = f'В Excel файле отсутствуют обязательные колонки:\n\n{chr(10).join(missing_details)}\n\nПожалуйста, добавьте эти колонки в файл и повторите импорт.'
    
    # Добавляем примечание для ВНИИ в дополнительных соглашениях
    if is_supplement and federal_operator == 'VNII':
        message += "\n\nПримечание: Для договоров ВНИИ колонки 'Регионы реализации', 'Дата начала' и 'Дата окончания' не обязательны."
    
    return message
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
@require_http_methods(["GET"])
def get_supplement_quotas(request, pk):
    """Получение истории квот (квот, которые были заменены дополнительными соглашениями)"""
    agreement = get_object_or_404(EduAgreement, pk=pk)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            # Проверяем, есть ли подписанные дополнительные соглашения
            signed_supplements = agreement.supplements.filter(
                status=Supplement.SupplementStatus.SIGNED
            ).order_by('-signing_date', '-created_at')
            
            if signed_supplements.exists():
                # Если есть подписанные дополнительные соглашения, показываем неактивные квоты
                # (те, что были заменены при импорте дополнительных соглашений)
                historical_quotas = agreement.quotas.filter(is_active=False).select_related('education_program').prefetch_related('regions')
                context_message = "Эти квоты были заменены в результате применения дополнительных соглашений."
            else:
                # Если нет подписанных дополнительных соглашений, показываем все квоты как исторические
                # (поскольку без подписанного договора или доп. соглашения квоты не действуют)
                historical_quotas = agreement.quotas.all().select_related('education_program').prefetch_related('regions')
                context_message = "Квоты не действуют, так как основной договор не подписан и нет подписанных дополнительных соглашений."
            
            total_places = 0
            programs_set = set()
            
            for quota in historical_quotas:
                total_places += quota.quantity
                programs_set.add(quota.education_program.id)
            
            if historical_quotas.exists():
                # Генерируем HTML для таблицы исторических квот
                status_badge = 'bg-warning text-dark' if signed_supplements.exists() else 'bg-secondary'
                status_text = 'Заменена' if signed_supplements.exists() else 'Неактивна'
                
                html = f'''
                <div class="table-responsive">
                    <table class="table table-sm table-striped mb-0 quotas-table">
                        <thead class="table-secondary">
                            <tr>
                                <th style="min-width: 300px;">Программа обучения</th>
                                <th style="min-width: 200px;">Регионы реализации</th>
                                <th style="min-width: 80px;">Количество мест</th>
                                <th style="min-width: 100px;">Стоимость за заявку</th>
                                <th style="min-width: 120px;">Общая стоимость</th>
                                <th style="min-width: 140px;">Период обучения</th>
                                <th style="min-width: 120px;">Статус</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                
                for quota in historical_quotas:
                    html += f'''
                        <tr class="table-secondary">
                            <td class="text-start">
                                <div class="d-flex flex-column">
                                    <strong>{quota.education_program.name}</strong>
                                    <small class="text-muted">
                                        {quota.education_program.get_program_type_display()} • 
                                        {quota.education_program.academic_hours} ч. • 
                                        {quota.education_program.get_study_form_display()}
                                    </small>
                                </div>
                            </td>
                            <td class="text-start regions-cell">
                                {quota.regions_display}
                            </td>
                            <td>
                                <span class="badge bg-secondary">{quota.quantity} мест</span>
                            </td>
                            <td>
                                <span class="badge bg-secondary">{quota.formatted_cost_per_quota}</span>
                            </td>
                            <td>
                                <span class="badge bg-secondary">{quota.formatted_total_cost}</span>
                            </td>
                            <td class="period-cell">
                                <div class="d-flex flex-column">
                    '''
                    if quota.formatted_start_date:
                        html += f'<span class="text-muted">{quota.formatted_start_date}</span>'
                    if quota.formatted_end_date:
                        html += f'<span class="text-muted">{quota.formatted_end_date}</span>'
                    if not quota.formatted_start_date and not quota.formatted_end_date:
                        html += '<span class="text-muted">—</span>'
                    
                    html += f'''
                                </div>
                            </td>
                            <td>
                                <span class="badge {status_badge}">{status_text}</span>
                            </td>
                        </tr>
                    '''
                
                html += f'''
                        </tbody>
                    </table>
                </div>
                <div class="alert alert-warning mt-3 mb-0">
                    <i class="bi bi-info-circle me-2"></i>
                    <strong>Историческая информация:</strong> {context_message}
                </div>
                '''
            else:
                html = '''
                <div class="alert alert-info mb-0">
                    <i class="bi bi-info-circle me-2"></i>
                    По данному договору нет исторических данных о квотах.
                </div>
                '''
            
            return JsonResponse({
                'success': True,
                'html': html,
                'program_count': len(programs_set),
                'total_places': total_places
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Ошибка загрузки квот: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Метод не поддерживается'
    })


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
            
            # Для ВНИИ даты и регионы не обязательны
            if agreement.federal_operator == 'VNII':
                start_date = None
                end_date = None
            
            quota = Quota.objects.create(
                agreement=agreement,
                education_program_id=data['program_id'],
                quantity=data['quantity'],
                cost_per_quota=data.get('cost_per_quota', 0),
                start_date=start_date,
                end_date=end_date
            )
            # Добавляем выбранные регионы (для ВНИИ регионы могут отсутствовать)
            region_ids = data.get('regions', [])
            if region_ids and agreement.federal_operator != 'VNII':
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
            
            # Обработка дат (для ВНИИ даты игнорируются)
            if agreement.federal_operator != 'VNII':
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
            else:
                # Для ВНИИ очищаем даты
                quota.start_date = None
                quota.end_date = None
            
            quota.save()
            
            # Обновляем регионы если они переданы (для ВНИИ регионы могут отсутствовать)
            if agreement.federal_operator != 'VNII':
                region_ids = data.get('regions', [])
                if region_ids:
                    quota.regions.set(region_ids)
                elif 'regions' in data:
                    # Если передан пустой список, очищаем регионы
                    quota.regions.clear()
            
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
            'signing_date': supplement.signing_date.strftime('%Y-%m-%d') if supplement.signing_date else '',
            'signing_date_display': supplement.signing_date.strftime('%d.%m.%Y') if supplement.signing_date else 'Не подписано',
            'status': supplement.status,
            'status_display': supplement.get_status_display(),
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
@csrf_exempt
@require_http_methods(["POST"])
def edit_supplement(request, pk):
    """Редактирование дополнительного соглашения"""
    supplement = get_object_or_404(Supplement, pk=pk)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            
            # Обновляем поля дополнительного соглашения
            supplement.number = data.get('number', supplement.number)
            supplement.description = data.get('description', supplement.description)
            supplement.status = data.get('status', supplement.status)
            
            # Обновляем дату подписания если предоставлена
            if 'signing_date' in data and data['signing_date']:
                try:
                    from datetime import datetime
                    supplement.signing_date = datetime.strptime(data['signing_date'], '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            supplement.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Дополнительное соглашение успешно обновлено'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Ошибка при обновлении дополнительного соглашения: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Метод не поддерживается'
    })


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
                'message': get_missing_columns_message(missing_columns, is_supplement=False)
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
            'message': get_missing_columns_message(missing_columns, is_supplement=False)
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
                
                # Ищем договор сначала, чтобы проверить федерального оператора
                agreement = EduAgreement.objects.filter(number=agreement_number).first()
                if not agreement:
                    errors.append(f'Строка {index + 2}: Договор {agreement_number} не найден')
                    error_count += 1
                    continue

                # Для ВНИИ регионы не обязательны
                required_fields = [agreement_number, program_name]
                if agreement.federal_operator != 'VNII':
                    required_fields.append(regions_text)
                
                if not all(required_fields):
                    errors.append(f'Строка {index + 2}: Отсутствуют обязательные данные')
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
                            'дпо пк': EducationProgram.ProgramType.ADVANCED,
                            'повышение квалификации': EducationProgram.ProgramType.ADVANCED,
                            'профессиональная переподготовка': EducationProgram.ProgramType.PROFESSIONAL_RE,
                            'профессиональное обучение': EducationProgram.ProgramType.PROFESSIONAL,
                            'программы профессионального обучения': EducationProgram.ProgramType.PROFESSIONAL
                        }
                        
                        program_type_key = program_type.lower()
                        program_type_value = program_type_choices.get(program_type_key, EducationProgram.ProgramType.ADVANCED)
                        
                        # Определяем форму обучения
                        study_form_choices = {
                            'очная': EducationProgram.StudyForm.FULL_TIME,
                            'заочная': EducationProgram.StudyForm.DISTANCE,
                            'очно-заочная': EducationProgram.StudyForm.PART_TIME,
                            'дистанционная': EducationProgram.StudyForm.DISTANCE
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
                
                # Для ВНИИ регионы не обязательны
                if not regions and agreement.federal_operator != 'VNII':
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
                'message': get_missing_columns_message(missing_columns, is_supplement=False)
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
                                'повышение квалификации': EducationProgram.ProgramType.ADVANCED,
                                'профессиональная переподготовка': EducationProgram.ProgramType.PROFESSIONAL_RE,
                                'программы профессионального обучения': EducationProgram.ProgramType.PROFESSIONAL,
                                'профессиональное обучение': EducationProgram.ProgramType.PROFESSIONAL
                            }
                            
                            program_type_key = program_type.lower()
                            program_type_value = program_type_choices.get(program_type_key, EducationProgram.ProgramType.ADVANCED)
                            
                            # Определяем форму обучения
                            study_form_choices = {
                                'очная': EducationProgram.StudyForm.FULL_TIME,
                                'заочная': EducationProgram.StudyForm.DISTANCE,
                                'очно-заочная': EducationProgram.StudyForm.PART_TIME,
                                'дистанционная': EducationProgram.StudyForm.DISTANCE
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

                    # Парсим регионы с использованием пользовательских выборов (для ВНИИ регионы не обязательны)
                    regions_names = []
                    regions = []
                    
                    if agreement.federal_operator != 'VNII' and regions_text:
                        regions_names = [clean_text_data(name) for name in regions_text.split(',') if clean_text_data(name)]
                    
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
                    
                    # Для ВНИИ регионы не обязательны
                    if not regions and agreement.federal_operator != 'VNII':
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
                        start_date=start_date,
                        end_date=end_date,
                        cost_per_quota=float(row['стоимость_за_заявку']),
                        is_active=True
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
        required_columns = ['Программа обучения', 'Форма обучения', 'Длительность', 'Количество мест']
        # Для не-ВНИИ регионы обязательны
        if agreement.federal_operator != 'VNII':
            required_columns.append('Регионы реализации')
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return JsonResponse({
                'success': False,
                'message': get_missing_columns_message(missing_columns, is_supplement=True, federal_operator=agreement.federal_operator)
            })
        
        # Очищаем и парсим данные
        new_quotas = []
        unrecognized_regions = set()
        
        for index, row in df.iterrows():
            if pd.isna(row['Программа обучения']) or pd.isna(row['Количество мест']) or pd.isna(row['Длительность']):
                continue
            
            program_name = clean_text_data(str(row['Программа обучения']))
            study_form_text = clean_text_data(str(row.get('Форма обучения', '')))
            duration_text = clean_text_data(str(row.get('Длительность', '')))
            # Для ВНИИ регионы не обязательны
            if agreement.federal_operator != 'VNII':
                regions_text = clean_text_data(str(row.get('Регионы реализации', '')))
            else:
                regions_text = ''
            
            try:
                quantity = int(row['Количество мест'])
            except (ValueError, TypeError):
                continue
            
            # Парсим стоимость за заявку
            cost_per_quota = None
            if 'Стоимость за заявку' in row and pd.notna(row['Стоимость за заявку']):
                try:
                    cost_str = str(row['Стоимость за заявку']).replace(' ', '').replace(',', '.')
                    # Убираем символы валюты
                    cost_str = re.sub(r'[^\d.,]', '', cost_str)
                    if cost_str and cost_str != 'nan':
                        cost_per_quota = float(cost_str)
                except (ValueError, TypeError):
                    pass
            
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
            
            # Не фильтруем по типу программы, так как колонка содержит форму обучения
            
            # Фильтруем по длительности
            if duration:
                programs = programs.filter(academic_hours=duration)
            
            if programs.exists():
                program = programs.first()
            else:
                # Автоматически создаём программу если не найдена
                try:
                    default_type = EducationProgram.ProgramType.ADVANCED
                    study_form_map = {
                        'очная': EducationProgram.StudyForm.FULL_TIME,
                        'заочная': EducationProgram.StudyForm.DISTANCE,
                        'очно-заочная': EducationProgram.StudyForm.PART_TIME,
                        'дистанционная': EducationProgram.StudyForm.DISTANCE
                    }
                    study_form_value = study_form_map.get(study_form_text.lower(), EducationProgram.StudyForm.FULL_TIME) if study_form_text else EducationProgram.StudyForm.FULL_TIME
                    program = EducationProgram.objects.create(
                        name=program_name,
                        program_type=default_type,
                        academic_hours=duration,
                        study_form=study_form_value,
                        description='Автоматически создана при анализе доп. соглашения'
                    )
                except Exception as e:
                    error_parts = [program_name]
                    if study_form_text:
                        error_parts.append(f"форма: {study_form_text}")
                    if duration:
                        error_parts.append(f"длительность: {duration} ч.")
                    
                    return JsonResponse({
                        'success': False,
                        'message': f'Не удалось создать программу: {" | ".join(error_parts)}. Ошибка: {str(e)}'
                    })
            
            # Парсим регионы
            regions_names = []
            if regions_text:  # Проверяем, что regions_text не пустой
                for name in regions_text.split(','):
                    cleaned_name = clean_text_data(name)
                    if cleaned_name:
                        # Убираем содержимое в скобках
                        cleaned_name = re.sub(r'\([^)]*\)', '', cleaned_name).strip()
                        if cleaned_name:
                            regions_names.append(cleaned_name)
            
            # Проверяем регионы (для ВНИИ регионы не обязательны)
            valid_regions = []
            if agreement.federal_operator != 'VNII':
                for region_name in regions_names:
                    region, match_type = find_region_without_creating(region_name)
                    if match_type != 'not_found' and region:
                        valid_regions.append(region.name)
                    else:
                        unrecognized_regions.add(region_name)
                
                # Для не-ВНИИ должны быть регионы
                if valid_regions:
                    new_quotas.append({
                        'program_id': program.id,
                        'program_name': program.name,
                        'regions': valid_regions,
                        'quantity': quantity,
                        'cost_per_quota': cost_per_quota
                    })
            else:
                # Для ВНИИ добавляем квоту без регионов
                new_quotas.append({
                    'program_id': program.id,
                    'program_name': program.name,
                    'regions': [],
                    'quantity': quantity,
                    'cost_per_quota': cost_per_quota
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
        supplement_signing_date = request.POST.get('supplement_signing_date', '')
        supplement_status = request.POST.get('supplement_status', 'NEGOTIATION')
        
        if not supplement_number:
            return JsonResponse({'success': False, 'message': 'Номер дополнительного соглашения обязателен'})
        
        # Валидация статуса
        valid_statuses = [choice[0] for choice in Supplement.SupplementStatus.choices]
        if supplement_status not in valid_statuses:
            supplement_status = 'NEGOTIATION'
        
        agreement_id = file_data['agreement_id']
        
        try:
            agreement = EduAgreement.objects.get(id=agreement_id)
        except EduAgreement.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Договор не найден'})
        
        # Читаем данные из сессии повторно
        df_data = request.session.get('supplement_df_data')
        if not df_data:
            return JsonResponse({'success': False, 'message': 'Данные Excel файла не найдены'})
        
        # Используем StringIO для корректного чтения JSON
        import io
        df = pd.read_json(io.StringIO(df_data))
        created_quotas = []
        

        
        with transaction.atomic():
            # Обрабатываем дату подписания
            signing_date = None
            if supplement_signing_date:
                try:
                    from datetime import datetime
                    signing_date = datetime.strptime(supplement_signing_date, '%Y-%m-%d').date()
                except ValueError:
                    signing_date = None
            
            # Создаем дополнительное соглашение
            supplement = Supplement.objects.create(
                agreement=agreement,
                number=supplement_number,
                description=supplement_description or f'Импорт из файла {file_name}',
                status=supplement_status,
                signing_date=signing_date
            )
            
            # 1. Деактивируем все старые квоты
            agreement.quotas.update(is_active=False)
            
            # 2. Создаем новые квоты из файла
            for index, row in df.iterrows():
                try:
                    program_name = clean_text_data(str(row['Программа обучения']))
                    study_form_text = clean_text_data(str(row.get('Форма обучения', '')))
                    duration_text = clean_text_data(str(row.get('Длительность', '')))
                    # Для ВНИИ регионы не обязательны
                    if agreement.federal_operator != 'VNII':
                        regions_text = clean_text_data(str(row.get('Регионы реализации', '')))
                    else:
                        regions_text = ''
                    
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
                    
                    # Не фильтруем по типу программы, так как колонка содержит форму обучения
                    
                    if duration:
                        programs = programs.filter(academic_hours=duration)
                    
                    if not programs.exists():
                        # Автоматически создаём программу если не найдена
                        try:
                            default_type = EducationProgram.ProgramType.ADVANCED
                            study_form_map = {
                                'очная': EducationProgram.StudyForm.FULL_TIME,
                                'заочная': EducationProgram.StudyForm.DISTANCE,
                                'очно-заочная': EducationProgram.StudyForm.PART_TIME,
                                'дистанционная': EducationProgram.StudyForm.DISTANCE
                            }
                            study_form_value = study_form_map.get(study_form_text.lower(), EducationProgram.StudyForm.FULL_TIME) if study_form_text else EducationProgram.StudyForm.FULL_TIME
                            program = EducationProgram.objects.create(
                                name=program_name,
                                program_type=default_type,
                                academic_hours=duration,
                                study_form=study_form_value,
                                description='Автоматически создана при анализе доп. соглашения'
                            )
                        except Exception:
                            continue
                    else:
                        program = programs.first()
                    
                    # Парсим регионы (для ВНИИ регионы не обязательны)
                    valid_regions = []
                    if agreement.federal_operator != 'VNII' and regions_text:
                        regions_names = [clean_text_data(name.strip()) for name in regions_text.split(',')]
                        regions_names = [name for name in regions_names if name]
                        
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
                        
                        # Для не-ВНИИ регионы обязательны
                        if not valid_regions:
                            continue
                    
                    # Парсим даты (для ВНИИ даты не обрабатываются)
                    start_date = None
                    end_date = None
                    cost_per_quota = None
                    
                    if agreement.federal_operator != 'VNII':
                        # Дата начала
                        if 'Дата начала' in row and pd.notna(row['Дата начала']):
                            try:
                                from datetime import datetime
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
                                from datetime import datetime
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
                            # Убираем символы валюты
                            import re
                            cost_str = re.sub(r'[^\d.,]', '', cost_str)
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


@login_required
def quota_summary_dashboard(request):
    """Сводный дашборд квот, потребностей и заявок"""
    from datetime import datetime, timedelta
    from crm_connector.models import AtlasApplication
    
    # Предварительно загружаем данные Atlas в кеш (если их еще нет)
    AtlasDataCache.get_cached_atlas_data()
    
    # Получаем только активные квоты по ИРПО
    irpo_agreements = EduAgreement.objects.filter(
        federal_operator='IRPO',
        status__in=[EduAgreement.AgreementStatus.SIGNED, EduAgreement.AgreementStatus.COMPLETED]
    )
    
    quotas = Quota.objects.filter(
        agreement__in=irpo_agreements,
        is_active=True
    ).select_related('education_program', 'agreement').prefetch_related('regions', 'demands', 'distributions')
    
    # Группируем квоты по программам
    programs_data = {}
    
    for quota in quotas:
        program_id = quota.education_program.id
        program_name = quota.education_program.name
        
        if program_id not in programs_data:
            programs_data[program_id] = {
                'program': quota.education_program,
                'quotas': [],
                'total_quota': 0,
                'total_demand': 0,
                'total_applications': 0,
                'coverage_percent': 0
            }
        
        # Подсчитываем потребности для квоты
        demands = quota.demands.filter(status=Demand.DemandStatus.ACTIVE)
        total_demand = demands.aggregate(total=models.Sum('quantity'))['total'] or 0
        
        # Получаем распределение квот по регионам
        distributions = []
        if quota.regions.count() > 1:
            # Если квота на несколько регионов, проверяем распределение
            for region in quota.regions.all():
                distribution = quota.distributions.filter(region=region).first()
                # Если распределения нет, создаем его с нулевым количеством
                if not distribution:
                    distribution = QuotaDistribution.objects.create(
                        quota=quota,
                        region=region,
                        allocated_quantity=0
                    )
                allocated = distribution.allocated_quantity
                
                # Потребности для региона и конкретного периода
                region_demands = demands.filter(
                    region=region,
                    start_date=quota.start_date,
                    end_date=quota.end_date
                )
                # Также включаем потребности без указания дат (старые записи)
                region_demands_legacy = demands.filter(
                    region=region,
                    start_date__isnull=True,
                    end_date__isnull=True
                )
                region_demands = region_demands | region_demands_legacy
                region_demand_quantity = region_demands.aggregate(total=models.Sum('quantity'))['total'] or 0
                
                # Заявки для региона (с фильтрацией по дате квоты)
                region_applications = get_matching_applications_by_region(quota, region, quota.start_date)
                
                # Процент покрытия для региона
                region_coverage = calculate_coverage_percent(allocated, region_demand_quantity, region_applications['total'])
                
                distributions.append({
                    'region': region,
                    'allocated': allocated,
                    'demands': region_demands,
                    'total_demand': region_demand_quantity,
                    'applications': region_applications,
                    'coverage_percent': region_coverage['main'],
                    'coverage_by_demand': region_coverage['by_demand'],
                    'coverage_by_quota': region_coverage['by_quota']
                })
        else:
            # Если квота на один регион
            region = quota.regions.first()
            if region:
                # Потребности для региона и конкретного периода
                region_demands = demands.filter(
                    region=region,
                    start_date=quota.start_date,
                    end_date=quota.end_date
                )
                # Также включаем потребности без указания дат (старые записи)
                region_demands_legacy = demands.filter(
                    region=region,
                    start_date__isnull=True,
                    end_date__isnull=True
                )
                region_demands = region_demands | region_demands_legacy
                region_demand_quantity = region_demands.aggregate(total=models.Sum('quantity'))['total'] or 0
                
                # Заявки для региона (с фильтрацией по дате квоты)
                region_applications = get_matching_applications_by_region(quota, region, quota.start_date)
                
                # Процент покрытия для региона
                region_coverage = calculate_coverage_percent(quota.quantity, region_demand_quantity, region_applications['total'])
                
                distributions.append({
                    'region': region,
                    'allocated': quota.quantity,
                    'demands': region_demands,
                    'total_demand': region_demand_quantity,
                    'applications': region_applications,
                    'coverage_percent': region_coverage['main'],
                    'coverage_by_demand': region_coverage['by_demand'],
                    'coverage_by_quota': region_coverage['by_quota']
                })
        
        # Подсчитываем общие заявки для квоты (сумма по всем регионам)
        applications_data = {'submitted': 0, 'in_training': 0, 'completed': 0, 'total': 0}
        for dist in distributions:
            applications_data['submitted'] += dist['applications']['submitted']
            applications_data['in_training'] += dist['applications']['in_training']
            applications_data['completed'] += dist['applications']['completed']
            applications_data['total'] += dist['applications']['total']
        
        # Рассчитываем покрытие для всей квоты
        quota_coverage = calculate_coverage_percent(quota.quantity, total_demand, applications_data['total'])
        
        quota_data = {
            'quota': quota,
            'distributions': distributions,
            'total_demand': total_demand,
            'demands': demands,
            'applications': applications_data,
            'coverage_percent': quota_coverage['main'],
            'coverage_by_demand': quota_coverage['by_demand'],
            'coverage_by_quota': quota_coverage['by_quota']
        }
        
        programs_data[program_id]['quotas'].append(quota_data)
        programs_data[program_id]['total_quota'] += quota.quantity
        programs_data[program_id]['total_demand'] += total_demand
        programs_data[program_id]['total_applications'] += applications_data['total']
    
    # Пересчитываем общий процент покрытия для каждой программы
    for program_id in programs_data:
        data = programs_data[program_id]
        program_coverage = calculate_coverage_percent(
            data['total_quota'],
            data['total_demand'],
            data['total_applications']
        )
        data['coverage_percent'] = program_coverage['main']
        data['coverage_by_demand'] = program_coverage['by_demand']
        data['coverage_by_quota'] = program_coverage['by_quota']
        
        # Группируем данные по регионам для правильного отображения rowspan
        data['quotas_by_region'] = group_quotas_by_region(data['quotas'])
    
    # Получаем несопоставленные заявки
    unmatched_applications = get_unmatched_applications()
    
    # Получаем список всех РОИВ для выпадающих списков
    roivs = ROIV.objects.filter(is_active=True).select_related('region').order_by('region__name', 'name')
    
    context = {
        'programs_data': programs_data,
        'unmatched_applications': unmatched_applications,
        'total_quotas': sum(p['total_quota'] for p in programs_data.values()),
        'total_demands': sum(p['total_demand'] for p in programs_data.values()),
        'total_applications': sum(p['total_applications'] for p in programs_data.values()),
        'roivs': roivs,
    }
    
    return render(request, 'education_planner/quota_summary_dashboard.html', context)


def get_matching_applications(quota):
    """Получить заявки, соответствующие квоте (общая функция)"""
    applications_data = {
        'submitted': 0,
        'in_training': 0,
        'completed': 0,
        'total': 0,
        'list': []
    }
    
    # Суммируем заявки по всем регионам квоты (с фильтрацией по дате квоты)
    for region in quota.regions.all():
        region_data = get_matching_applications_by_region(quota, region, quota.start_date)
        applications_data['submitted'] += region_data['submitted']
        applications_data['in_training'] += region_data['in_training']
        applications_data['completed'] += region_data['completed']
        applications_data['total'] += region_data['total']
        applications_data['list'].extend(region_data['list'])
    
    return applications_data


@cache_atlas_data(timeout=7200)  # Кеш на 2 часа
def get_matching_applications_by_region(quota, region, specific_date=None):
    """Получить заявки, соответствующие квоте в конкретном регионе"""
    from crm_connector.models import AtlasApplication, Deal, Pipeline, Stage
    from datetime import timedelta, datetime
    
    applications_data = {
        'submitted': 0,
        'in_training': 0,
        'completed': 0,
        'total': 0,
        'list': []
    }
    
    # Пытаемся получить данные из кеша
    pipeline, atlas_apps, deals = AtlasDataCache.get_cached_atlas_data()
    
    # Если данных нет в кеше, загружаем как обычно
    if not pipeline:
        pipeline = Pipeline.objects.filter(name='Заявки (граждане)').first()
        if not pipeline:
            return applications_data
            
    if not atlas_apps:
        atlas_apps = list(AtlasApplication.objects.select_related('deal').filter(deal__pipeline=pipeline))
    
    if not deals:
        deals = list(Deal.objects.select_related('stage').filter(pipeline=pipeline))
    
    # ТОЧНАЯ логика Atlas Dashboard
    # Создаем словарь сделка -> заявка как в Atlas Dashboard
    atlas_apps_dict = {}
    for app in atlas_apps:
        if app.deal_id:
            atlas_apps_dict[app.deal_id] = app  # Последняя запись перезаписывает (как в Atlas)
    
    # Теперь фильтруем по региону и программе через сделки
    applications = []
    
    for deal in deals:
        atlas_app = atlas_apps_dict.get(deal.id)
        if (atlas_app and 
            atlas_app.region == region.name and
            atlas_app.raw_data and
            quota.education_program.name.lower() in atlas_app.raw_data.get('Программа обучения', '').lower()):
            applications.append(atlas_app)
    
    # Исключаем скрытые этапы
    hidden_stages = ['1. Необработанная заявка', '2. Направлена инструкция по РвР']
    
    # Определяем целевую дату для сравнения
    target_date_str = None
    if specific_date:
        target_date_str = specific_date.strftime('%d.%m.%Y')
    elif quota.start_date:
        target_date_str = quota.start_date.strftime('%d.%m.%Y')
    
    for app in applications:
        if app.deal and app.deal.stage and app.deal.stage.name not in hidden_stages:
            # ВАЖНО: фильтруем по конкретной дате если указана
            if target_date_str and app.raw_data:
                app_start_str = app.raw_data.get('Начало периода обучения', '')
                if app_start_str != target_date_str:
                    continue  # Пропускаем заявки с другой датой
            
            stage_sort = app.deal.stage.sort
            
            # Считаем все заявки (как в Atlas Dashboard)
            applications_data['total'] += 1
            
            # Категоризируем по этапам согласно Atlas Dashboard
            if stage_sort in [30, 40, 50, 60]:  # Этапы 3-6: подача
                applications_data['submitted'] += 1
            elif stage_sort == 70:  # Этап 7: обучение
                applications_data['in_training'] += 1
            elif stage_sort == 80:  # Этап 8: завершили
                applications_data['completed'] += 1
    
    applications_data['list'] = list(applications[:5])
    
    return applications_data


@cache_atlas_data(timeout=7200)  # Кеш на 2 часа
def get_unmatched_applications():
    """Получить заявки, которые не соответствуют ни одной квоте"""
    from crm_connector.models import AtlasApplication, AtlasStatus
    
    # Получаем все активные квоты ИРПО
    irpo_agreements = EduAgreement.objects.filter(
        federal_operator='IRPO',
        status__in=[EduAgreement.AgreementStatus.SIGNED, EduAgreement.AgreementStatus.COMPLETED]
    )
    
    active_quotas = Quota.objects.filter(
        agreement__in=irpo_agreements,
        is_active=True
    )
    
    # Получаем регионы из активных квот
    quota_regions = set()
    for quota in active_quotas:
        quota_regions.update(quota.regions.values_list('name', flat=True))
    
    # Используем кешированные статусы
    status_cache = AtlasDataCache.get_cached_atlas_statuses()
    
    # Минимальный порядок статуса для подсчета
    min_order = 60
    
    # Получаем все заявки с подходящим статусом
    all_valid_applications = []
    for app in AtlasApplication.objects.all()[:1000]:  # Ограничиваем для производительности
        atlas_status_name = app.raw_data.get('Статус заявки в Атлас', '') if app.raw_data else ''
        if atlas_status_name and atlas_status_name in status_cache:
            status_order = status_cache[atlas_status_name]
            if status_order >= min_order:
                all_valid_applications.append(app)
    
    # Из них выбираем те, которые не соответствуют регионам квот
    unmatched = []
    for app in all_valid_applications:
        if not quota_regions or app.region not in quota_regions:
            unmatched.append(app)
    
    return unmatched[:50]  # Ограничиваем количество для производительности


def calculate_coverage_percent(quota_quantity, demand_quantity, applications_quantity):
    """Рассчитать процент закрытия квоты
    
    Возвращает словарь с процентами покрытия:
    - by_demand: процент покрытия по потребности РОИВ
    - by_quota: процент покрытия по квоте
    - main: основной процент (по потребности, если есть, иначе по квоте)
    """
    result = {
        'by_demand': 0,
        'by_quota': 0,
        'main': 0
    }
    
    # Процент покрытия по потребности РОИВ
    if demand_quantity > 0:
        result['by_demand'] = (applications_quantity / demand_quantity) * 100
    
    # Процент покрытия по квоте
    if quota_quantity > 0:
        result['by_quota'] = (applications_quantity / quota_quantity) * 100
    
    # Основной процент (приоритет потребности)
    if demand_quantity > 0:
        result['main'] = result['by_demand']
    elif quota_quantity > 0:
        result['main'] = result['by_quota']
    
    return result


@cache_atlas_data(timeout=7200)  # Кеш на 2 часа
def get_applications_for_alternative_period(region, quota, start_str, end_str):
    """Получить заявки для альтернативного периода"""
    from crm_connector.models import AtlasApplication, Deal, Pipeline, Stage
    
    applications_data = {
        'submitted': 0, 'in_training': 0, 'completed': 0, 'total': 0, 'list': []
    }
    
    # Пытаемся получить данные из кеша
    pipeline, atlas_apps, deals = AtlasDataCache.get_cached_atlas_data()
    
    # Если данных нет в кеше, загружаем как обычно
    if not pipeline:
        pipeline = Pipeline.objects.filter(name='Заявки (граждане)').first()
        if not pipeline:
            return applications_data
            
    if not atlas_apps:
        atlas_apps = list(AtlasApplication.objects.select_related('deal').filter(deal__pipeline=pipeline))
    
    if not deals:
        deals = list(Deal.objects.select_related('stage').filter(pipeline=pipeline))
    
    # ТОЧНАЯ логика Atlas Dashboard
    # Создаем словарь сделка -> заявка как в Atlas Dashboard
    atlas_apps_dict = {}
    for app in atlas_apps:
        if app.deal_id:
            atlas_apps_dict[app.deal_id] = app  # Последняя запись перезаписывает (как в Atlas)
    
    # Теперь фильтруем по региону и программе через сделки
    applications = []
    
    for deal in deals:
        atlas_app = atlas_apps_dict.get(deal.id)
        if (atlas_app and 
            atlas_app.region == region.name and
            atlas_app.raw_data and
            quota.education_program.name.lower() in atlas_app.raw_data.get('Программа обучения', '').lower()):
            applications.append(atlas_app)
    
    # Исключаем скрытые этапы
    hidden_stages = ['1. Необработанная заявка', '2. Направлена инструкция по РвР']
    
    valid_applications = []
    processed_deal_ids = set()  # Дополнительная защита от дублей
    
    for app in applications:
        if app.raw_data and app.deal_id not in processed_deal_ids:
            # Проверяем программу
            app_program = app.raw_data.get('Программа обучения', '')
            if quota.education_program.name.lower() not in app_program.lower():
                continue
                
            # Проверяем дату начала
            app_start = app.raw_data.get('Начало периода обучения', '')
            if app_start != start_str:
                continue
                
            # Проверяем этап Deal
            if app.deal and app.deal.stage and app.deal.stage.name not in hidden_stages:
                stage_sort = app.deal.stage.sort
                
                processed_deal_ids.add(app.deal_id)
                valid_applications.append(app)
                
                # Считаем все заявки (как в Atlas Dashboard)
                applications_data['total'] += 1
                
                # Категоризируем по этапам согласно Atlas Dashboard
                if stage_sort in [30, 40, 50, 60]:  # Этапы 3-6: подача
                    applications_data['submitted'] += 1
                elif stage_sort == 70:  # Этап 7: обучение
                    applications_data['in_training'] += 1
                elif stage_sort == 80:  # Этап 8: завершили
                    applications_data['completed'] += 1
    
    applications_data['list'] = valid_applications[:5]
    
    return applications_data


@cache_atlas_data(timeout=7200)  # Кеш на 2 часа
def group_quotas_by_region(quotas):
    """Группирует квоты по регионам для правильного отображения rowspan"""
    from crm_connector.models import AtlasApplication
    from datetime import datetime, timedelta
    import numpy as np
    
    def business_days_between(start_date, end_date):
        """Подсчет рабочих дней между датами"""
        try:
            return int(np.busday_count(start_date, end_date))
        except:
            return 999  # Если ошибка, возвращаем большое число
    
    def find_alternative_periods(quota, region, existing_dates):
        """Найти альтернативные периоды из заявок в пределах 10 рабочих дней"""
        if not quota.start_date:
            return []
        
        # Ищем заявки для этого региона и программы
        apps = AtlasApplication.objects.filter(
            region=region.name,
            raw_data__icontains=quota.education_program.name  # Полное название программы
        )
        
        alternative_periods = set()
        main_start = quota.start_date
        
        for app in apps:
            if app.raw_data:
                app_start_str = app.raw_data.get('Начало периода обучения', '')
                app_end_str = app.raw_data.get('Окончание периода обучения', '')
                
                if app_start_str and app_end_str:
                    try:
                        app_start = datetime.strptime(app_start_str, '%d.%m.%Y').date()
                        app_end = datetime.strptime(app_end_str, '%d.%m.%Y').date()
                        
                        # Проверяем, что дата в пределах 10 рабочих дней
                        business_days = business_days_between(main_start, app_start)
                        
                        # ВАЖНО: исключаем даты, которые уже есть среди основных квот
                        if (0 < business_days <= 10 and 
                            app_start != main_start and 
                            app_start not in existing_dates):
                            
                            # Дополнительная проверка: есть ли активные заявки для этой даты
                            apps_for_period = get_applications_for_alternative_period(
                                region, quota, app_start_str, app_end_str
                            )
                            
                            # Добавляем альтернативный период только если есть заявки
                            if apps_for_period['total'] > 0:
                                alternative_periods.add((app_start, app_end, app_start_str, app_end_str))
                    except:
                        continue
        
        return list(alternative_periods)
    
    grouped = {}
    
    # Сначала собираем все существующие даты по регионам и программам
    existing_dates_by_region_program = {}
    
    for quota_data in quotas:
        for dist in quota_data['distributions']:
            region_id = dist['region'].id
            program_id = quota_data['quota'].education_program.id
            
            key = (region_id, program_id)
            if key not in existing_dates_by_region_program:
                existing_dates_by_region_program[key] = set()
            
            if quota_data['quota'].start_date:
                existing_dates_by_region_program[key].add(quota_data['quota'].start_date)
    
    # Теперь группируем данные
    for quota_data in quotas:
        for dist in quota_data['distributions']:
            region_id = dist['region'].id
            region_name = dist['region'].name
            
            if region_id not in grouped:
                grouped[region_id] = {
                    'region': dist['region'],
                    'rows': []
                }
            
            # Создаем основную строку данных для этого региона и квоты
            row_data = {
                'quota_data': quota_data,
                'distribution': dist,
                'is_alternative': False
            }
            
            grouped[region_id]['rows'].append(row_data)
    
    # Отдельно ищем альтернативные периоды для каждого региона и программы
    processed_alternatives = set()  # Чтобы не дублировать альтернативы
    
    for quota_data in quotas:
        for dist in quota_data['distributions']:
            region_id = dist['region'].id
            program_id = quota_data['quota'].education_program.id
            
            # Ключ для отслеживания уже обработанных комбинаций
            alt_key = (region_id, program_id)
            if alt_key in processed_alternatives:
                continue
            
            processed_alternatives.add(alt_key)
            
            # Получаем все существующие даты для этой программы в этом регионе
            existing_dates = existing_dates_by_region_program.get(alt_key, set())
            
            # Ищем альтернативные периоды
            alternative_periods = find_alternative_periods(quota_data['quota'], dist['region'], existing_dates)
            
            for alt_start, alt_end, alt_start_str, alt_end_str in alternative_periods:
                # Получаем заявки для альтернативного периода
                alt_applications = get_applications_for_alternative_period(
                    dist['region'], quota_data['quota'], alt_start_str, alt_end_str
                )
                
                # Получаем или создаем альтернативную квоту
                alt_quota, created = AlternativeQuota.objects.get_or_create(
                    quota=quota_data['quota'],
                    region=dist['region'],
                    start_date=alt_start,
                    end_date=alt_end,
                    defaults={'quantity': dist['allocated']}  # По умолчанию копируем количество из основной квоты
                )
                
                # Пересчитываем потребности для альтернативного периода
                alt_demands = quota_data['quota'].demands.filter(
                    status=Demand.DemandStatus.ACTIVE,
                    region=dist['region'],
                    start_date=alt_start,
                    end_date=alt_end
                )
                alt_demand_quantity = alt_demands.aggregate(total=models.Sum('quantity'))['total'] or 0
                
                # Создаем distribution для альтернативного периода
                alt_distribution = {
                    'region': dist['region'],
                    'allocated': alt_quota.quantity,  # Используем количество из альтернативной квоты
                    'alternative_start': alt_start,
                    'alternative_end': alt_end,
                    'alternative_start_str': alt_start_str,
                    'alternative_end_str': alt_end_str,
                    'applications': alt_applications,
                    'demands': alt_demands,
                    'total_demand': alt_demand_quantity,
                    'alt_quota_id': alt_quota.id  # Добавляем ID альтернативной квоты
                }
                
                # Рассчитываем покрытие для альтернативного периода
                alt_coverage = calculate_coverage_percent(
                    alt_quota.quantity, 
                    alt_demand_quantity, 
                    alt_applications['total']
                )
                alt_distribution['coverage_percent'] = alt_coverage['main']
                alt_distribution['coverage_by_demand'] = alt_coverage['by_demand']
                alt_distribution['coverage_by_quota'] = alt_coverage['by_quota']
                
                # Создаем строку для альтернативного периода
                alt_row_data = {
                    'quota_data': quota_data,
                    'distribution': alt_distribution,
                    'is_alternative': True
                }
                
                grouped[region_id]['rows'].append(alt_row_data)
    
    # Преобразуем в список для удобства в шаблоне
    result = []
    for region_data in grouped.values():
        region_data['rowspan'] = len(region_data['rows'])
        result.append(region_data)
    
    return result


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def manage_alternative_quota(request):
    """API для управления альтернативными квотами"""
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        if action == 'update':
            alt_quota = get_object_or_404(AlternativeQuota, pk=data['alt_quota_id'])
            
            # Валидация количества
            try:
                quantity = int(data['quantity'])
                if quantity <= 0:
                    return JsonResponse({
                        'success': False,
                        'message': 'Количество мест должно быть положительным числом'
                    })
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'message': 'Некорректное количество мест'
                })
            
            alt_quota.quantity = quantity
            alt_quota.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Альтернативная квота успешно обновлена'
            })
            
        else:
            return JsonResponse({
                'success': False,
                'message': 'Неподдерживаемое действие'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Ошибка: {str(e)}'
        })


@login_required
@csrf_exempt  
@require_http_methods(["GET", "POST", "PUT", "DELETE"])
def manage_roiv(request):
    """API для управления РОИВ"""
    from .models import ROIV, Region
    
    if request.method == 'GET':
        region_id = request.GET.get('region_id')
        if region_id:
            roivs = ROIV.objects.filter(region_id=region_id, is_active=True)
        else:
            roivs = ROIV.objects.filter(is_active=True)
        
        data = [{
            'id': roiv.id,
            'name': roiv.name,
            'full_name': roiv.full_name,
            'region_id': roiv.region_id,
            'region_name': roiv.region.name,
            'contact_info': roiv.contact_info
        } for roiv in roivs]
        
        return JsonResponse({'roivs': data})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            region = Region.objects.get(id=data['region_id'])
            
            roiv = ROIV.objects.create(
                name=data['name'],
                region=region,
                full_name=data.get('full_name', ''),
                contact_info=data.get('contact_info', '')
            )
            
            return JsonResponse({
                'success': True,
                'roiv': {
                    'id': roiv.id,
                    'name': roiv.name,
                    'full_name': roiv.full_name,
                    'region_id': roiv.region_id,
                    'region_name': roiv.region.name
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Method not allowed'})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def manage_demand(request):
    """Управление потребностями РОИВ"""
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        if action == 'create':
            quota = get_object_or_404(Quota, pk=data['quota_id'])
            roiv = get_object_or_404(ROIV, pk=data['roiv_id'])
            
            # Валидация количества
            try:
                quantity = int(data['quantity'])
                if quantity <= 0:
                    return JsonResponse({
                        'success': False,
                        'message': 'Количество мест должно быть положительным числом'
                    })
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'message': 'Некорректное количество мест'
                })
            
            # Получаем даты периода из запроса
            start_date = None
            end_date = None
            if data.get('start_date'):
                from datetime import datetime
                start_date = datetime.strptime(data['start_date'], '%d.%m.%Y').date()
            if data.get('end_date'):
                from datetime import datetime  
                end_date = datetime.strptime(data['end_date'], '%d.%m.%Y').date()
            
            demand = Demand.objects.create(
                quota=quota,
                roiv=roiv,
                region=roiv.region,  # Автоматически заполняется из РОИВ
                quantity=quantity,
                document_link=data.get('document_link', ''),
                comment=data.get('comment', ''),
                start_date=start_date,
                end_date=end_date,
                created_by=request.user
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Потребность успешно создана',
                'demand_id': demand.id
            })
            
        elif action == 'update':
            demand = get_object_or_404(Demand, pk=data['demand_id'])
            
            # Валидация количества при обновлении
            if 'quantity' in data:
                try:
                    quantity = int(data['quantity'])
                    if quantity <= 0:
                        return JsonResponse({
                            'success': False,
                            'message': 'Количество мест должно быть положительным числом'
                        })
                    demand.quantity = quantity
                except (ValueError, TypeError):
                    return JsonResponse({
                        'success': False,
                        'message': 'Некорректное количество мест'
                    })
            
            # Обновляем остальные поля
            demand.document_link = data.get('document_link', demand.document_link)
            demand.comment = data.get('comment', demand.comment)
            demand.status = data.get('status', demand.status)
            demand.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Потребность успешно обновлена'
            })
            
        elif action == 'delete':
            demand = get_object_or_404(Demand, pk=data['demand_id'])
            demand.status = Demand.DemandStatus.CANCELLED
            demand.save()
            
            # Создаем запись в истории
            DemandHistory.objects.create(
                demand=demand,
                action=DemandHistory.ActionType.CANCELLED,
                quantity_before=demand.quantity,
                quantity_after=0,
                user=request.user,
                comment='Потребность отменена'
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Потребность отменена'
            })
            
        elif action == 'get':
            demand = get_object_or_404(Demand, pk=data['demand_id'])
            
            return JsonResponse({
                'success': True,
                'demand': {
                    'id': demand.id,
                    'quantity': demand.quantity,
                    'document_link': demand.document_link or '',
                    'comment': demand.comment or '',
                    'roiv': {
                        'id': demand.roiv.id,
                        'name': demand.roiv.name,
                        'region_name': demand.roiv.region.name
                    },
                    'start_date': demand.start_date.strftime('%d.%m.%Y') if demand.start_date else '',
                    'end_date': demand.end_date.strftime('%d.%m.%Y') if demand.end_date else ''
                }
            })
            
        elif action == 'get_history':
            demand = get_object_or_404(Demand, pk=data['demand_id'])
            history = demand.history.all()
            
            history_data = []
            for h in history:
                history_data.append({
                    'action': h.get_action_display(),
                    'quantity_before': h.quantity_before,
                    'quantity_after': h.quantity_after,
                    'user': h.user.get_full_name() if h.user else 'Система',
                    'comment': h.comment,
                    'created_at': h.created_at.strftime('%d.%m.%Y %H:%M')
                })
            
            return JsonResponse({
                'success': True,
                'history': history_data
            })
            
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка: {str(e)}'})


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def distribute_quota(request):
    """Распределение квоты между регионами"""
    try:
        data = json.loads(request.body)
        quota = get_object_or_404(Quota, pk=data['quota_id'])
        distributions = data.get('distributions', [])
        
        # Проверяем, что сумма распределений не превышает квоту
        total_allocated = sum(d['quantity'] for d in distributions)
        if total_allocated > quota.quantity:
            return JsonResponse({
                'success': False,
                'message': f'Сумма распределений ({total_allocated}) превышает квоту ({quota.quantity})'
            })
        
        # Удаляем старые распределения
        quota.distributions.all().delete()
        
        # Создаем новые распределения
        for dist in distributions:
            region = get_object_or_404(Region, pk=dist['region_id'])
            QuotaDistribution.objects.create(
                quota=quota,
                region=region,
                allocated_quantity=dist['quantity']
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Квота успешно распределена'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Ошибка: {str(e)}'})
