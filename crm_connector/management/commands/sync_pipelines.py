from django.core.management.base import BaseCommand
from crm_connector.bitrix24_api import Bitrix24API

class Command(BaseCommand):
    help = 'Синхронизирует воронки продаж и их этапы с Битрикс24'

    def handle(self, *args, **options):
        self.stdout.write('Начинаем синхронизацию воронок продаж с Битрикс24...')
        
        try:
            api = Bitrix24API()
            
            # Проверяем подключение перед синхронизацией
            if not api.test_api_connection():
                self.stdout.write(self.style.ERROR('Не удалось подключиться к API Битрикс24'))
                return
                
            result = api.sync_pipelines_and_stages()
            
            self.stdout.write(self.style.SUCCESS(
                f'Успешно синхронизировано {result["pipelines_count"]} воронок и {result["stages_count"]} этапов!'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при синхронизации: {str(e)}')) 