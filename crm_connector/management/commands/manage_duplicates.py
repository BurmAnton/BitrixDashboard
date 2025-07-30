import logging
import re
from django.core.management.base import BaseCommand
from django.utils import timezone
from crm_connector.models import Deal, Pipeline, AtlasApplication
from crm_connector.bitrix24_api import Bitrix24API

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Поиск и удаление дублированных сделок в указанной воронке'
    
    def __init__(self):
        super().__init__()
        self.api = None
        self.pipeline = None
        self.stats = {
            'duplicate_deals_removed': 0,
            'errors': 0
        }
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--pipeline-name',
            type=str,
            default='Заявки (граждане)',
            help='Название воронки в Битрикс24'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Запуск в режиме тестирования (без удаления)'
        )
        parser.add_argument(
            '--list-only',
            action='store_true',
            help='Только показать дубликаты без удаления'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Начинаем поиск дублированных сделок...'))
        
        # Инициализация
        self.api = Bitrix24API()
        
        # Находим воронку
        try:
            self.pipeline = Pipeline.objects.get(name=options['pipeline_name'])
            self.stdout.write(f"Работаем с воронкой: {self.pipeline.name}")
        except Pipeline.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Воронка '{options['pipeline_name']}' не найдена!"))
            return
        
        # Поиск и удаление дубликатов
        self.find_and_remove_duplicates(options['dry_run'] or options['list_only'])
        
        # Вывод статистики
        self.print_statistics()
    
    def find_and_remove_duplicates(self, dry_run=False):
        """
        Находит и удаляет дублированные сделки в воронке, оставляя самую старую.
        """
        self.stdout.write("Поиск дублированных сделок...")
        
        # Получаем все сделки из воронки
        deals = Deal.objects.filter(pipeline=self.pipeline).order_by('created_at', 'bitrix_id')
        self.stdout.write(f"Всего сделок в воронке: {deals.count()}")
        
        # Группируем сделки по ключам для поиска дубликатов
        deal_groups = {}
        
        for deal in deals:
            # Безопасно работаем с деталями сделки
            deal_details = deal.details or {}
            
            # Извлекаем и нормализуем данные
            deal_name = deal_details.get('NAME', '') or deal_details.get('TITLE', '')
            deal_phone = self.extract_phone_from_deal(deal_details)
            deal_email = self.extract_email_from_deal(deal_details)
            deal_snils = self.extract_snils_from_deal(deal_details)
            
            name_norm = self.normalize_name(deal_name)
            phone_norm = self.normalize_phone(deal_phone)
            email_norm = self.normalize_email(deal_email)
            snils_norm = self.normalize_snils(deal_snils)
            
            # Пропускаем сделки без основных данных
            if not name_norm and not phone_norm and not email_norm and not snils_norm:
                continue
                
            # Создаем ключи для группировки
            duplicate_keys = []
            
            # СНИЛС - самый надежный критерий (если есть)
            if snils_norm:
                duplicate_keys.append(('snils', snils_norm))
            
            # Ключ по ФИО + телефон
            if name_norm and phone_norm:
                duplicate_keys.append(('name_phone', name_norm, phone_norm))
                
            # Ключ по ФИО + email  
            if name_norm and email_norm:
                duplicate_keys.append(('name_email', name_norm, email_norm))
                
            # Ключ по ФИО + СНИЛС
            if name_norm and snils_norm:
                duplicate_keys.append(('name_snils', name_norm, snils_norm))
                
            # Ключ по телефону (если есть и ФИО)
            if phone_norm and name_norm:
                duplicate_keys.append(('phone', phone_norm))
                
            # Ключ по email (если есть и ФИО)
            if email_norm and name_norm:
                duplicate_keys.append(('email', email_norm))
            
            # Добавляем сделку в группы по всем подходящим ключам
            for key in duplicate_keys:
                if key not in deal_groups:
                    deal_groups[key] = []
                deal_groups[key].append(deal)
        
        # Находим группы с дубликатами
        duplicates_to_remove = []
        
        for key, group_deals in deal_groups.items():
            if len(group_deals) > 1:
                # Сортируем по дате создания (самые старые первыми)
                sorted_deals = sorted(group_deals, key=lambda d: (
                    d.created_at or timezone.now(),
                    d.bitrix_id
                ))
                
                # Оставляем самую старую, остальные помечаем для удаления
                keep_deal = sorted_deals[0]
                remove_deals = sorted_deals[1:]
                
                self.stdout.write(f"🔍 Найдена группа дубликатов по ключу {key[0]}:")
                self.stdout.write(f"  ✅ Оставляем: сделка {keep_deal.bitrix_id} (создана: {keep_deal.created_at})")
                
                for deal in remove_deals:
                    self.stdout.write(f"  ❌ Удаляем: сделка {deal.bitrix_id} (создана: {deal.created_at})")
                    if deal not in duplicates_to_remove:
                        duplicates_to_remove.append(deal)
        
        # Удаляем дубликаты
        if duplicates_to_remove:
            self.stdout.write(f"\n📊 Найдено {len(duplicates_to_remove)} дублированных сделок для удаления")
            
            if not dry_run:
                # Удаляем через batch API для эффективности
                self._delete_deals_in_batches(duplicates_to_remove)
                self.stdout.write(f"✅ Удалено {self.stats['duplicate_deals_removed']} дублированных сделок")
            else:
                self.stdout.write("🧪 ТЕСТОВЫЙ РЕЖИМ: дубликаты не удалены")
        else:
            self.stdout.write("✅ Дублированных сделок не найдено")
    
    def _delete_deals_in_batches(self, deals_to_delete):
        """Удаляет сделки пакетами через Битрикс24 API"""
        batch_size = 50  # Максимальный размер batch для Битрикс24
        
        for i in range(0, len(deals_to_delete), batch_size):
            batch = deals_to_delete[i:i + batch_size]
            
            # Подготавливаем команды для batch удаления
            batch_commands = {}
            for j, deal in enumerate(batch):
                cmd_key = f"delete_{deal.bitrix_id}"
                batch_commands[cmd_key] = [
                    'crm.deal.delete',
                    {'id': deal.bitrix_id}
                ]
            
            self.stdout.write(f"Удаляем пакет сделок из Битрикс24 ({len(batch)} шт.): {[d.bitrix_id for d in batch]}")
            
            try:
                # Выполняем batch удаление в Битрикс24
                result = self.api.call_batch(batch_commands)
                
                # Проверяем результаты и удаляем успешные сделки из локальной базы
                if result and 'result' in result:
                    batch_results = result['result']
                    errors = result['result'].get('result_error', {})
                    
                    for j, deal in enumerate(batch):
                        cmd_key = f"delete_{deal.bitrix_id}"
                        
                        # Проверяем есть ли ошибка для этой команды
                        if cmd_key in errors and errors[cmd_key]:
                            error_info = errors[cmd_key]
                            error_desc = error_info.get('error_description', '') if isinstance(error_info, dict) else str(error_info)
                            
                            # Если сделка не найдена - это не критичная ошибка, сделка уже удалена
                            if 'not found' in error_desc.lower() or 'не найден' in error_desc.lower():
                                self.stdout.write(f"⚠️ Сделка {deal.bitrix_id} уже удалена из Битрикс24")
                                # Удаляем из локальной базы
                                self._remove_deal_locally(deal)
                            else:
                                logger.error(f"Ошибка при удалении сделки {deal.bitrix_id} из Битрикс24: {error_info}")
                                self.stdout.write(self.style.ERROR(f"Не удалось удалить сделку {deal.bitrix_id}: {error_desc}"))
                            continue
                        
                        # Если нет ошибки, удаляем локально
                        self._remove_deal_locally(deal)
                
                else:
                    logger.error(f"Неожиданный ответ batch API: {result}")
                    self.stdout.write(self.style.ERROR("Ошибка batch удаления: неожиданный ответ API"))
                    
                    # Пробуем удалить по одной сделке
                    for deal in batch:
                        self._delete_single_deal(deal)
                        
            except Exception as e:
                logger.error(f"Критическая ошибка при batch удалении: {e}")
                self.stdout.write(self.style.ERROR(f"Ошибка batch удаления: {e}"))
                
                # Пробуем удалить по одной сделке
                for deal in batch:
                    self._delete_single_deal(deal)
    
    def _remove_deal_locally(self, deal):
        """Удаляет сделку из локальной базы данных"""
        try:
            # Удаляем связанные AtlasApplication записи
            AtlasApplication.objects.filter(deal=deal).delete()
            
            # Удаляем из локальной базы
            deal.delete()
            
            self.stats['duplicate_deals_removed'] += 1
            self.stdout.write(f"✅ Удалена дублированная сделка {deal.bitrix_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при удалении сделки {deal.bitrix_id} из локальной базы: {e}")
            self.stdout.write(self.style.ERROR(f"Ошибка при локальном удалении сделки {deal.bitrix_id}: {e}"))
    
    def _delete_single_deal(self, deal):
        """Удаляет одну сделку через обычный API (fallback для batch)"""
        try:
            self.stdout.write(f"Удаляем сделку {deal.bitrix_id} по отдельности...")
            
            # Удаляем из Битрикс24 через обычный API
            result = self.api.call_method('crm.deal.delete', {'id': deal.bitrix_id})
            
            if result:
                self._remove_deal_locally(deal)
            else:
                logger.error(f"API вернул пустой результат при удалении сделки {deal.bitrix_id}")
                self.stdout.write(self.style.ERROR(f"Не удалось удалить сделку {deal.bitrix_id}: пустой ответ API"))
                
        except Exception as e:
            error_msg = str(e)
            
            # Если сделка не найдена - это не критичная ошибка
            if 'not found' in error_msg.lower() or 'не найден' in error_msg.lower():
                self.stdout.write(f"⚠️ Сделка {deal.bitrix_id} уже удалена из Битрикс24")
                self._remove_deal_locally(deal)
            else:
                logger.error(f"Ошибка при удалении сделки {deal.bitrix_id}: {e}")
                self.stdout.write(self.style.ERROR(f"Не удалось удалить сделку {deal.bitrix_id}: {e}"))
    
    def extract_phone_from_deal(self, deal_details):
        """Извлекает телефон из деталей сделки"""
        phone_fields = ['PHONE', 'UF_CRM_PHONE', 'UF_CRM_1234567890123']  # Может быть разные поля
        for field in phone_fields:
            phone = deal_details.get(field, '')
            if phone:
                return phone
        return ''
    
    def extract_email_from_deal(self, deal_details):
        """Извлекает email из деталей сделки"""
        email_fields = ['EMAIL', 'UF_CRM_EMAIL', 'UF_CRM_1234567890124']  # Может быть разные поля
        for field in email_fields:
            email = deal_details.get(field, '')
            if email:
                return email
        return ''
    
    def extract_snils_from_deal(self, deal_details):
        """Извлекает СНИЛС из деталей сделки"""
        if not deal_details:
            return ''
        
        # СНИЛС хранится в кастомном поле UF_CRM_1750933149374
        snils_field = 'UF_CRM_1750933149374'
        snils = deal_details.get(snils_field, '')
        
        # Также проверяем альтернативные поля на случай изменений
        if not snils:
            alternative_fields = ['UF_CRM_SNILS', 'SNILS', 'UF_SNILS']
            for field in alternative_fields:
                snils = deal_details.get(field, '')
                if snils:
                    break
        
        return str(snils) if snils else ''
    
    def normalize_name(self, name):
        """Нормализует ФИО для сравнения"""
        if not name:
            return ''
        
        # Приводим к нижнему регистру и убираем лишние пробелы
        normalized = ' '.join(name.lower().split())
        
        # Убираем точки после инициалов
        normalized = normalized.replace('.', '')
        
        return normalized
    
    def normalize_phone(self, phone):
        """Нормализует телефон для сравнения"""
        if not phone:
            return ''
        
        # Оставляем только цифры
        digits = ''.join(filter(str.isdigit, str(phone)))
        
        # Убираем код страны если есть
        if digits.startswith('7') and len(digits) == 11:
            digits = digits[1:]
        elif digits.startswith('8') and len(digits) == 11:
            digits = digits[1:]
        
        return digits
    
    def normalize_email(self, email):
        """Нормализует email для сравнения"""
        if not email:
            return ''
        
        return email.lower().strip()
    
    def normalize_snils(self, snils):
        """Нормализует СНИЛС для сравнения"""
        if not snils:
            return ''
        
        # Оставляем только цифры
        digits = re.sub(r'[^\d]', '', str(snils))
        
        # СНИЛС должен быть 11 цифр
        if len(digits) == 11:
            return digits
        
        return ''
    
    def print_statistics(self):
        """Выводит статистику"""
        self.stdout.write("\n" + "="*50)
        self.stdout.write("СТАТИСТИКА ПОИСКА ДУБЛИКАТОВ:")
        self.stdout.write(f"Удалено дублированных сделок: {self.stats['duplicate_deals_removed']}")
        self.stdout.write(f"Ошибок: {self.stats['errors']}")
        self.stdout.write("="*50 + "\n") 