from celery import shared_task
from django.utils import timezone
from datetime import datetime
import pytz
from .bitrix24_api import Bitrix24API
from .models import Lead, Deal, Contact, Pipeline, Stage
import logging

logger = logging.getLogger(__name__)

@shared_task
def sync_leads():
    """Задача для синхронизации лидов из Битрикс24"""
    api = Bitrix24API()
    leads = api.get_all_leads()
    
    for lead_data in leads:
        # Конвертация строки времени в datetime
        created_at = datetime.strptime(
            lead_data['DATE_CREATE'], '%Y-%m-%dT%H:%M:%S%z'
        )
        
        Lead.objects.update_or_create(
            bitrix_id=lead_data['ID'],
            defaults={
                'title': lead_data['TITLE'],
                'name': lead_data.get('NAME', ''),
                'phone': lead_data.get('PHONE', [{}])[0].get('VALUE', '') if lead_data.get('PHONE') else '',
                'email': lead_data.get('EMAIL', [{}])[0].get('VALUE', '') if lead_data.get('EMAIL') else '',
                'status': lead_data['STATUS_ID'],
                'created_at': created_at,
            }
        )
    
    return f"Синхронизировано {len(leads)} лидов"

@shared_task
def sync_deals():
    """Задача для синхронизации сделок из Битрикс24"""
    api = Bitrix24API()
    deals = api.get_all_deals()
    
    current_time = timezone.now()
    synced_count = 0
    
    for deal_data in deals:
        # Конвертация строки времени в datetime
        created_at = datetime.strptime(
            deal_data['DATE_CREATE'], '%Y-%m-%dT%H:%M:%S%z'
        )
        
        closed_at = None
        if deal_data.get('CLOSEDATE'):
            closed_at = datetime.strptime(
                deal_data['CLOSEDATE'], '%Y-%m-%dT%H:%M:%S%z'
            )
        
        deal, created = Deal.objects.update_or_create(
            bitrix_id=deal_data['ID'],
            defaults={
                'title': deal_data['TITLE'],
                'stage': deal_data['STAGE_ID'],
                'amount': deal_data.get('OPPORTUNITY', 0),
                'created_at': created_at,
                'closed_at': closed_at,
                'last_sync': current_time
            }
        )
        synced_count += 1
    
    return f"Синхронизировано {synced_count} сделок"

@shared_task
def sync_contacts():
    """Задача для синхронизации контактов из Битрикс24"""
    api = Bitrix24API()
    contacts = api.get_all_contacts()
    
    for contact_data in contacts:
        # Конвертация строки времени в datetime
        created_at = datetime.strptime(
            contact_data['DATE_CREATE'], '%Y-%m-%dT%H:%M:%S%z'
        )
        
        Contact.objects.update_or_create(
            bitrix_id=contact_data['ID'],
            defaults={
                'name': contact_data['NAME'],
                'last_name': contact_data.get('LAST_NAME', ''),
                'phone': contact_data.get('PHONE', [{}])[0].get('VALUE', '') if contact_data.get('PHONE') else '',
                'email': contact_data.get('EMAIL', [{}])[0].get('VALUE', '') if contact_data.get('EMAIL') else '',
                'created_at': created_at,
            }
        )
    
    return f"Синхронизировано {len(contacts)} контактов"

@shared_task
def sync_pipelines_task():
    """Задача для синхронизации воронок из Битрикс24"""
    try:
        # Получаем API-клиент
        api = Bitrix24API()
        
        # Получаем данные о воронках
        pipelines_data = api.get_all('crm.pipeline.list')
        
        for pipeline_data in pipelines_data:
            pipeline_id = pipeline_data.get('ID')
            
            # Создаем или обновляем воронку
            pipeline, created = Pipeline.objects.update_or_create(
                id=pipeline_id,
                defaults={
                    'name': pipeline_data.get('NAME', ''),
                    'sort': int(pipeline_data.get('SORT', 0)),
                    'is_main': pipeline_data.get('IS_MAIN', 'N') == 'Y'
                }
            )
            
            # Получаем этапы для этой воронки
            stages_data = api.get_all('crm.status.list', {
                'filter': {'ENTITY_ID': f'DEAL_STAGE_{pipeline_id}'}
            })
            
            for stage_data in stages_data:
                stage_id = stage_data.get('STATUS_ID')
                
                # Определяем тип этапа на основе имени или других параметров
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
                    id=stage_id,
                    defaults={
                        'pipeline': pipeline,
                        'name': name,
                        'sort': int(stage_data.get('SORT', 0)),
                        'type': stage_type,
                        'color': stage_data.get('COLOR', '')
                    }
                )
        
        return True
    
    except Exception as e:
        # Логирование ошибки
        logger.error(f"Ошибка при синхронизации воронок: {str(e)}")
        return False

@shared_task
def sync_deals_full():
    """Задача для полной синхронизации сделок из Битрикс24"""
    api = Bitrix24API()
    print("Запуск полной синхронизации сделок...")
    deals = api.get_all_deals()
    
    if not deals:
        print("❌ Не удалось получить сделки из API")
        return "Ошибка: не удалось получить сделки из API"
    
    # Используем логику из команды синхронизации
    current_time = timezone.now()
    
    # Получаем все воронки и этапы для быстрого доступа
    pipelines = {p.bitrix_id: p for p in Pipeline.objects.all()}
    stages = {s.bitrix_id: s for s in Stage.objects.all()}
    
    synced_count = 0
    
    for deal_data in deals:
        try:
            # Конвертация строки времени в datetime
            created_at = datetime.strptime(
                deal_data['DATE_CREATE'], '%Y-%m-%dT%H:%M:%S%z'
            )
            
            closed_at = None
            if deal_data.get('CLOSEDATE'):
                closed_at = datetime.strptime(
                    deal_data['CLOSEDATE'], '%Y-%m-%dT%H:%M:%S%z'
                )
            
            # Получаем воронку и этап
            pipeline_id = str(deal_data.get('CATEGORY_ID', '0'))
            stage_id = deal_data.get('STAGE_ID', '')
            
            pipeline = pipelines.get(pipeline_id)
            stage = stages.get(stage_id)
            
            # Проверяем, существует ли уже сделка
            deal_exists = Deal.objects.filter(bitrix_id=deal_data['ID']).exists()
            
            # Безопасное преобразование в int с обработкой None
            try:
                category_id = int(pipeline_id) if pipeline_id else 0
            except (ValueError, TypeError):
                category_id = 0
                
            try:
                probability = int(deal_data.get('PROBABILITY', 0)) if deal_data.get('PROBABILITY') is not None else 0
            except (ValueError, TypeError):
                probability = 0
                
            try:
                amount = float(deal_data.get('OPPORTUNITY', 0)) if deal_data.get('OPPORTUNITY') is not None else 0
            except (ValueError, TypeError):
                amount = 0
            
            # Сохраняем сделку
            deal, created = Deal.objects.update_or_create(
                bitrix_id=deal_data['ID'],
                defaults={
                    'title': deal_data['TITLE'],
                    'pipeline': pipeline,
                    'stage': stage,
                    'amount': amount,
                    'created_at': created_at,
                    'closed_at': closed_at,
                    'responsible_id': deal_data.get('ASSIGNED_BY_ID'),
                    'category_id': category_id,
                    'is_closed': deal_data.get('CLOSED') == 'Y',
                    'is_new': not deal_exists,
                    'probability': probability,
                    'details': deal_data,
                    'last_sync': current_time
                }
            )
            
            synced_count += 1
        except Exception as e:
            print(f"Ошибка при обработке сделки {deal_data.get('ID')}: {str(e)}")
    
    return f"Синхронизировано {synced_count} сделок" 