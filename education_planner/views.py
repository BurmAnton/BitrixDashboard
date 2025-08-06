from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Sum, Prefetch
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import transaction
from .forms import EducationProgramForm, ProgramSectionFormSet
from .models import (
    EducationProgram, EduAgreement, Quota, Supplement, QuotaChange, Region
)
import json
import pandas as pd

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


@login_required
@require_http_methods(["POST"])
def import_quotas_excel(request):
    """Импорт квот из Excel файла"""
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
        file_name = f'temp_import_{timezone.now().timestamp()}_{excel_file.name}'
        file_path = default_storage.save(file_name, ContentFile(excel_file.read()))
        full_path = default_storage.path(file_path)
        
        # Читаем Excel файл
        df = pd.read_excel(full_path)
        
        # Проверяем необходимые колонки
        required_columns = [
            'договор_номер', 'программа_название', 'программа_часы', 
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
                    # Ищем договор
                    agreement = EduAgreement.objects.filter(
                        number=str(row['договор_номер']).strip()
                    ).first()
                    
                    if not agreement:
                        errors.append(f'Строка {index + 2}: Договор {row["договор_номер"]} не найден')
                        error_count += 1
                        continue

                    # Ищем программу обучения
                    program = EducationProgram.objects.filter(
                        name__icontains=str(row['программа_название']).strip(),
                        academic_hours=int(row['программа_часы'])
                    ).first()
                    
                    if not program:
                        errors.append(f'Строка {index + 2}: Программа "{row["программа_название"]}" ({row["программа_часы"]} ч.) не найдена')
                        error_count += 1
                        continue

                    # Парсим регионы
                    regions_names = [name.strip() for name in str(row['регионы']).split(',')]
                    regions = []
                    for region_name in regions_names:
                        region = Region.objects.filter(name__icontains=region_name).first()
                        if region:
                            regions.append(region)
                        else:
                            errors.append(f'Строка {index + 2}: Регион "{region_name}" не найден')
                    
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
        # Удаляем временный файл в случае ошибки
        try:
            if 'full_path' in locals() and os.path.exists(full_path):
                os.remove(full_path)
        except:
            pass
        
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
                'договор_номер', 'программа_название', 'программа_часы', 'программа_форма',
                'регионы', 'количество', 'стоимость_за_заявку', 'дата_начала', 'дата_окончания'
            ],
            'Описание': [
                'Номер договора (должен существовать в системе)',
                'Название программы обучения (должна существовать в системе)',
                'Количество академических часов программы',
                'Форма обучения (Очная/Заочная/Очно-заочная)',
                'Регионы через запятую (должны существовать в системе)',
                'Количество мест по квоте (целое число)',
                'Стоимость обучения одного человека (число с точкой)',
                'Дата начала обучения в формате ДД.ММ.ГГГГ (необязательно)',
                'Дата окончания обучения в формате ДД.ММ.ГГГГ (необязательно)'
            ],
            'Обязательность': [
                'Обязательно', 'Обязательно', 'Обязательно', 'Обязательно',
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
