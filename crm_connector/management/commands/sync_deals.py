from django.core.management.base import BaseCommand
from django.utils import timezone
from crm_connector.bitrix24_api import Bitrix24API
from crm_connector.models import Deal, Pipeline, Stage
import datetime
import json

class Command(BaseCommand):
    help = 'Синхронизирует сделки из Битрикс24'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=0, 
                            help='Количество дней для синхронизации (по умолчанию 30)')
        parser.add_argument('--all', action='store_true', 
                            help='Синхронизировать все сделки')
        parser.add_argument('--pipeline', type=str, 
                            help='ID воронки для синхронизации')

    def handle(self, *args, **options):
        self.stdout.write('Начинаем синхронизацию сделок с Битрикс24...')
        
        try:
            api = Bitrix24API()
            
            # Проверяем подключение перед синхронизацией
            if not api.test_api_connection():
                self.stdout.write(self.style.ERROR('Не удалось подключиться к API Битрикс24'))
                return
            
            # Получаем сделки из Битрикс24
            if options['all']:
                self.stdout.write('Синхронизация всех сделок...')
                deals = api.get_all_deals()
            elif options['pipeline']:
                self.stdout.write(f'Синхронизация сделок для воронки {options["pipeline"]}...')
                deals = api.get_deals_by_pipeline(options['pipeline'])
            else:
                days = options['days']
                if days <= 0:
                    # Если days=0, получаем все сделки
                    self.stdout.write('Синхронизация всех сделок (days=0)...')
                    deals = api.get_all_deals()
                else:
                    self.stdout.write(f'Синхронизация сделок за последние {days} дней...')
                    start_date = timezone.now() - datetime.timedelta(days=days)
                    deals = api.get_deals_by_date(start_date)
            
            count = self.sync_deals(deals)
            
            self.stdout.write(self.style.SUCCESS(f'Успешно синхронизировано {count} сделок!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при синхронизации: {str(e)}'))
    
    def sync_deals(self, deals):
        """Синхронизирует сделки с БД"""
        synced_count = 0
        current_time = timezone.now()
        
        # Получаем все воронки и этапы для быстрого доступа
        pipelines = {p.bitrix_id: p for p in Pipeline.objects.all()}
        stages = {s.bitrix_id: s for s in Stage.objects.all()}
        
        for deal_data in deals:
            try:
                # Конвертация строки времени в datetime
                created_at = datetime.datetime.strptime(
                    deal_data['DATE_CREATE'], '%Y-%m-%dT%H:%M:%S%z'
                )
                
                closed_at = None
                if deal_data.get('CLOSEDATE'):
                    closed_at = datetime.datetime.strptime(
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
        
        return synced_count 