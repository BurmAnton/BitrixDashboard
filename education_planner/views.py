from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Sum, Prefetch
from django.core.paginator import Paginator
from django.utils import timezone
from .forms import EducationProgramForm, ProgramSectionFormSet
from .models import (
    EducationProgram, EduAgreement, Quota, Supplement, QuotaChange, Region
)
import json

# Create your views here.

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
