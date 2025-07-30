import os
import json
import pandas as pd
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.utils import timezone
from crm_connector.models import Deal, Pipeline, Stage, AtlasApplication, StageRule
from crm_connector.bitrix24_api import Bitrix24API
import logging
import re

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Импорт заявок из выгрузки платформы Атлас'
    
    def __init__(self):
        super().__init__()
        self.api = None
        self.field_mapping = None
        self.pipeline = None
        # Кэш для порядковых номеров статусов
        self._status_order_cache = {"atlas": {}, "rr": {}}
        self.stats = {
            'updated_deals': 0,
            'deleted_deals': 0,
            'duplicate_deals_removed': 0,
            'matched_applications': 0,
            'new_applications': 0,
            'updated_applications': 0,
            'created_deals': 0,
            'errors': 0
        }
    
    def add_arguments(self, parser):
        parser.add_argument(
            'excel_file',
            type=str,
            help='Путь к Excel файлу с выгрузкой из Атласа'
        )
        parser.add_argument(
            '--pipeline-name',
            type=str,
            default='Заявки (граждане)',
            help='Название воронки в Битрикс24'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Запуск в режиме тестирования (без изменений)'
        )
        parser.add_argument(
            '--no-delete',
            action='store_true',
            help='Не удалять сделки, отсутствующие в Битрикс24'
        )
        parser.add_argument(
            '--no-remove-duplicates',
            action='store_true',
            help='Не удалять дублированные сделки'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Начинаем импорт заявок из Атласа...'))
        
        # Инициализация
        self.api = Bitrix24API()
        self.load_field_mapping()
        
        # 1. Обновление данных по сделкам из воронки
        self.update_deals_from_bitrix(options['pipeline_name'], options['no_delete'])
        
        # 2. Поиск и удаление дублированных сделок
        if not options['no_remove_duplicates']:
            self.find_and_remove_duplicates(options['dry_run'])
        else:
            self.stdout.write("Пропускаем поиск дубликатов (опция --no-remove-duplicates)")
        
        # 3. Загрузка данных из Excel
        applications_data = self.load_excel_data(options['excel_file'])
        
        # 4. Сопоставление и обработка заявок
        self.process_applications(applications_data, options['dry_run'])
        
        # Вывод статистики
        self.print_statistics()
    
    def load_field_mapping(self):
        """Загружает маппинг полей из JSON файла"""
        mapping_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'atlas_field_mapping.json'
        )
        
        with open(mapping_file, 'r', encoding='utf-8') as f:
            self.field_mapping = json.load(f)
            
        self.stdout.write(f"Загружен маппинг полей из {mapping_file}")
    
    def update_deals_from_bitrix(self, pipeline_name, no_delete=False):
        """Обновляет данные по сделкам из указанной воронки в Битрикс24"""
        self.stdout.write(f"Обновляем данные по сделкам из воронки '{pipeline_name}'...")
        
        # Находим воронку
        try:
            self.pipeline = Pipeline.objects.get(name=pipeline_name)
        except Pipeline.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Воронка '{pipeline_name}' не найдена!"))
            self.stdout.write("Синхронизируем воронки...")
            # Синхронизируем воронки
            pipelines_data = self.api.get_all('crm.category.list', {'entityTypeId': 2})
            for p_data in pipelines_data:
                Pipeline.objects.update_or_create(
                    bitrix_id=p_data['ID'],
                    defaults={
                        'name': p_data['NAME'],
                        'sort': int(p_data.get('SORT', 0)),
                        'is_main': p_data.get('IS_DEFAULT', 'N') == 'Y',
                        'last_sync': timezone.now()
                    }
                )
            
            # Пробуем снова найти воронку
            self.pipeline = Pipeline.objects.get(name=pipeline_name)
        
        # Получаем все сделки из воронки
        deals_data = self.api.get_all('crm.deal.list', {
            'filter': {'CATEGORY_ID': self.pipeline.bitrix_id},
            'select': ['*', 'UF_*']
        })
        
        # Сохраняем ID существующих сделок
        existing_deal_ids = set()
        
        with transaction.atomic():
            for deal_data in deals_data:
                existing_deal_ids.add(int(deal_data['ID']))
                
                # Обновляем или создаем сделку
                deal, created = Deal.objects.update_or_create(
                    bitrix_id=deal_data['ID'],
                    defaults={
                        'title': deal_data.get('TITLE', ''),
                        'pipeline': self.pipeline,
                        'stage': self._get_or_create_stage(deal_data.get('STAGE_ID')),
                        'amount': float(deal_data.get('OPPORTUNITY', 0) or 0),
                        'created_at': self._parse_datetime(deal_data.get('DATE_CREATE')),
                        'closed_at': self._parse_datetime(deal_data.get('CLOSEDATE')),
                        'is_closed': deal_data.get('CLOSED', 'N') == 'Y',
                        'details': deal_data,
                        'last_sync': timezone.now()
                    }
                )
                
                if not created:
                    self.stats['updated_deals'] += 1
            
            # Удаляем сделки, которых нет в Битрикс24
            if not no_delete:
                deleted_count = Deal.objects.filter(
                    pipeline=self.pipeline
                ).exclude(
                    bitrix_id__in=existing_deal_ids
                ).delete()[0]
                
                self.stats['deleted_deals'] = deleted_count
                if deleted_count > 0:
                    self.stdout.write(f"Удалено {deleted_count} сделок, отсутствующих в Битрикс24")
        
        self.stdout.write(f"Обновлено {self.stats['updated_deals']} сделок")
    
    def find_and_remove_duplicates(self, dry_run=False):
        """
        Находит и удаляет дублированные сделки в воронке, оставляя самую старую.
        
        Критерии дубликатов:
        1. Одинаковые ФИО (нормализованные)
        2. Одинаковые телефоны или email
        3. В одной воронке
        """
        self.stdout.write("Поиск дублированных сделок...")
        
        if not self.pipeline:
            self.stdout.write("Воронка не определена, пропускаем поиск дубликатов")
            return
            
        # Получаем все сделки из воронки
        deals = Deal.objects.filter(pipeline=self.pipeline).order_by('created_at', 'bitrix_id')
        
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
                
                self.stdout.write(f"Найдена группа дубликатов по ключу {key[0]}: "
                                f"оставляем сделку {keep_deal.bitrix_id}, "
                                f"удаляем {len(remove_deals)} дубликатов")
                
                for deal in remove_deals:
                    if deal not in duplicates_to_remove:  # Избегаем повторных добавлений
                        duplicates_to_remove.append(deal)
        
        # Удаляем дубликаты
        if duplicates_to_remove:
            self.stdout.write(f"Найдено {len(duplicates_to_remove)} дублированных сделок для удаления")
            
            if not dry_run:
                # Удаляем через batch API для эффективности
                self._delete_deals_in_batches(duplicates_to_remove)
                        
                self.stdout.write(f"Удалено {self.stats['duplicate_deals_removed']} дублированных сделок")
            else:
                self.stdout.write("ТЕСТОВЫЙ РЕЖИМ: дубликаты не удалены")
                for deal in duplicates_to_remove:
                    self.stdout.write(f"  → Будет удалена сделка {deal.bitrix_id}")
        else:
            self.stdout.write("Дублированных сделок не найдено")
    
    def _delete_deals_in_batches(self, deals_to_delete):
        """
        Удаляет сделки пакетами через Битрикс24 API для повышения эффективности
        """
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
        """
        Удаляет сделку из локальной базы данных
        """
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
        """
        Удаляет одну сделку через обычный API (fallback для batch)
        """
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
    
    def load_excel_data(self, excel_file):
        """Загружает данные из Excel файла"""
        self.stdout.write(f"Загружаем данные из файла {excel_file}...")
        
        try:
            df = pd.read_excel(excel_file)
            self.stdout.write(f"Загружено {len(df)} строк")
            
            # Преобразуем DataFrame в список словарей
            applications = []
            for index, row in df.iterrows():
                app_data = {}
                for col in df.columns:
                    value = row[col]
                    # Обработка NaN значений
                    if pd.isna(value):
                        app_data[col] = None
                    else:
                        app_data[col] = str(value).strip() if isinstance(value, str) else value
                
                applications.append(app_data)
            
            return applications
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Ошибка при загрузке Excel файла: {e}"))
            raise
    
    def process_applications(self, applications_data, dry_run=False):
        """Обрабатывает заявки: сопоставляет, обновляет, создает новые"""
        self.stdout.write("Обрабатываем заявки...")

        # ------------------------------------------------------------------
        #  Предварительный отбор: для каждого СНИЛС оставляем заявку
        #  с максимальным номером заявления на РР (актуальную)
        # ------------------------------------------------------------------

        applications_data = self._filter_actual_applications(applications_data)

        for app_data in applications_data:
            # 0. Быстрая проверка по уникальному application_id
            application_uid = str(app_data.get('ID заявки из РР', '')).strip()
            matched_deal = None
            if application_uid:
                try:
                    atlas_rec = AtlasApplication.objects.select_related('deal').get(application_id=application_uid)
                    matched_deal = atlas_rec.deal  # может быть None, если ранее не было сделки
                except AtlasApplication.DoesNotExist:
                    matched_deal = None
            try:
                # Извлекаем основные поля для сопоставления
                # Составляем ФИО из отдельных полей
                full_name = self.get_full_name(app_data)
                phone = self.normalize_phone(app_data.get('Контактная информация (телефон)', ''))
                email = self.normalize_email(app_data.get('Email', ''))
                region = app_data.get('Регион', '')
                
                # Пропускаем пустые записи
                if not full_name:
                    continue
                
                # Если по UID ничего не нашли, дополнительно проверяем существующие записи AtlasApplication
                if not matched_deal and (full_name or phone or email):
                    existing_atlas_apps = AtlasApplication.objects.filter(
                        models.Q(full_name=full_name) |
                        models.Q(phone=phone) if phone else models.Q() |
                        models.Q(email=email) if email else models.Q()
                    ).select_related('deal')
                    
                    if existing_atlas_apps.exists():
                        # Находим наиболее подходящую из существующих записей
                        for atlas_app in existing_atlas_apps:
                            if atlas_app.deal:  # Если есть связанная сделка
                                matched_deal = atlas_app.deal
                                self.stdout.write(f"Найдена существующая запись AtlasApplication для {full_name}: сделка {atlas_app.deal.bitrix_id}")
                                break
                
                # Если по UID и по AtlasApplication ничего не нашли, ищем совпадение по правилам
                if not matched_deal:
                    matched_deal = self.find_matching_deal(full_name, phone, email, region)
                
                if matched_deal:
                    self.stats['matched_applications'] += 1
                    if not dry_run:
                        # Проверяем, является ли это обновлением существующей заявки или новой заявкой
                        should_update = self.should_update_deal(matched_deal, app_data)
                        if should_update:
                            self.update_existing_deal(matched_deal, app_data)
                        else:
                            self.stdout.write(f"⚠️  Найдена новая заявка для {full_name}, но сделка {matched_deal.bitrix_id} уже существует. "
                                            f"Программа: {app_data.get('Направление обучения', 'Не указано')}. "
                                            f"Рассмотрите создание отдельной сделки.")
                            # Можно добавить логику создания новой сделки для другой программы
                            # или записи в лог для ручной обработки
                            self.stats['new_applications'] += 1
                            self.create_new_deal(app_data)
                else:
                    self.stats['new_applications'] += 1
                    if not dry_run:
                        self.create_new_deal(app_data)
                        
            except Exception as e:
                self.stats['errors'] += 1
                # Логируем стек для диагностики
                logger.exception("Ошибка при обработке заявки (application_id=%s, full_name=%s): %s", app_data.get('ID заявки из РР'), app_data.get('ФИО'), e)
                self.stdout.write(self.style.ERROR(f"Ошибка: {e}"))
    
    def find_matching_deal(self, full_name, phone, email, region):
        """
        Находит совпадающую сделку по правилам:
        1) Если совпадает ФИО и любое другое поле
        2) Если совпадает номер или почта
        3) При нескольких совпадениях берем с максимальным количеством совпадений
        """
        candidates = []
        
        # Получаем все сделки из воронки
        deals = Deal.objects.filter(pipeline=self.pipeline)
        
        # Получаем ID кастомного поля региона из маппинга (если есть)
        region_field_id = self.field_mapping['field_mapping'].get('Регион', {}).get('bitrix_field', '')

        for deal in deals:
            match_score = 0
            matches = []

            # Безопасно работаем с деталями сделки (могут быть None)
            deal_details = deal.details or {}

            # Извлекаем данные из сделки
            deal_name = deal_details.get('NAME', '') or deal_details.get('TITLE', '')
            deal_phone = self.extract_phone_from_deal(deal_details)
            deal_email = self.extract_email_from_deal(deal_details)
            # Регион может быть в кастомном поле
            if region_field_id:
                deal_region = deal_details.get(region_field_id, '')
            else:
                deal_region = ''
            
            # Нормализуем данные сделки
            deal_name_norm = self.normalize_name(deal_name)
            deal_phone_norm = self.normalize_phone(deal_phone)
            deal_email_norm = self.normalize_email(deal_email)
            
            # Проверяем совпадения
            name_match = deal_name_norm and full_name and deal_name_norm == full_name
            phone_match = deal_phone_norm and phone and deal_phone_norm == phone
            email_match = deal_email_norm and email and deal_email_norm == email
            region_match = deal_region and region and deal_region.lower() == region.lower()

            if name_match:
                match_score += 2  # ФИО важнее
                matches.append('name')
            if phone_match:
                match_score += 3  # Телефон самый важный
                matches.append('phone')
            if email_match:
                match_score += 3  # Email тоже важный
                matches.append('email')
            if region_match:
                match_score += 1
                matches.append('region')
            
            # Правило 1: ФИО + любое другое поле
            if name_match and len(matches) > 1:
                candidates.append((deal, match_score, matches))
            # Правило 2: Телефон или email
            elif phone_match or email_match:
                candidates.append((deal, match_score, matches))
        
        # Если нашли кандидатов по строгим правилам – выбираем с максимальным score
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_match = candidates[0]
            self.stdout.write(
                f"Найдено совпадение для {full_name}: "
                f"сделка {best_match[0].bitrix_id} "
                f"(совпадения: {', '.join(best_match[2])})"
            )
            return best_match[0]

        # Фолбэк: ищем сделки с полностью совпавшим ФИО
        name_matches = [
            d for d in deals
            if self.normalize_name((d.details or {}).get('NAME', '') or (d.details or {}).get('TITLE', '')) == full_name
        ]
        
        if len(name_matches) == 1:
            self.stdout.write(f"Фолбэк-совпадение по ФИО для {full_name}: сделка {name_matches[0].bitrix_id}")
            return name_matches[0]
        elif len(name_matches) > 1:
            # Если найдено несколько дублей, выбираем наиболее подходящую
            self.stdout.write(f"Найдено {len(name_matches)} дублей для {full_name}, выбираем наилучший")
            
            # Сортируем по приоритету: сначала с телефоном/email, затем по дате создания
            def sort_key(deal):
                details = deal.details or {}
                has_phone = bool(self.extract_phone_from_deal(details))
                has_email = bool(self.extract_email_from_deal(details))
                # Чем больше данных, тем выше приоритет
                data_score = (2 if has_phone else 0) + (2 if has_email else 0)
                # Также учитываем дату последней синхронизации (более свежие сделки предпочтительнее)
                sync_time = deal.last_sync or deal.created_at or timezone.now()
                return (-data_score, -sync_time.timestamp())  # Сортировка по убыванию
            
            name_matches.sort(key=sort_key)
            selected_deal = name_matches[0]
            
            self.stdout.write(f"Выбрана сделка {selected_deal.bitrix_id} как наиболее подходящая")
            return selected_deal

        return None
    
    def should_update_deal(self, deal, app_data):
        """
        Определяет, нужно ли обновить существующую сделку или создать новую.
        
        Args:
            deal: Найденная сделка в базе
            app_data: Данные заявки из Атласа
            
        Returns:
            bool: True если нужно обновить, False если создать новую сделку
        """
        try:
            # Проверяем, есть ли уже связанная запись AtlasApplication для этой сделки
            existing_atlas_apps = AtlasApplication.objects.filter(deal=deal)
            
            # Получаем ID заявки из данных
            app_id = app_data.get('ID заявки из РР', '')
            
            if existing_atlas_apps.exists():
                # Если есть существующие записи AtlasApplication для этой сделки
                for atlas_app in existing_atlas_apps:
                    # Если ID заявки совпадает - это обновление той же заявки
                    if atlas_app.application_id == app_id:
                        return True
                    
                    # Проверяем совпадение по ФИО и программе обучения
                    atlas_program = atlas_app.raw_data.get('Направление обучения', '') if atlas_app.raw_data else ''
                    new_program = app_data.get('Направление обучения', '')
                    
                    if atlas_program == new_program and atlas_app.full_name == self.get_full_name(app_data):
                        return True
                
                # Если это другая программа обучения или другая заявка - создаем новую сделку
                return False
            
            # Если нет связанных записей AtlasApplication - обновляем существующую сделку
            return True
            
        except Exception as e:
            logger.error(f"Ошибка в should_update_deal для сделки {deal.bitrix_id}: {e}")
            # В случае ошибки по умолчанию обновляем существующую сделку
            return True
    
    def update_existing_deal(self, deal, app_data):
        """Обновляет существующую сделку данными из заявки"""
        try:
            # Подготавливаем данные для обновления
            update_data = self.prepare_deal_data(app_data, is_update=True)

            # Определяем актуальную стадию и, при необходимости, добавляем в update
            stage_id = self.determine_stage(app_data)
            if stage_id:
                update_data['STAGE_ID'] = stage_id
                # При смене стадии может потребоваться уточнить CATEGORY_ID
                update_data['CATEGORY_ID'] = self.pipeline.bitrix_id
            
            # Обновляем через API с использованием batch (одна команда)
            from uuid import uuid4
            cmd_key = f"upd_{deal.bitrix_id}_{uuid4().hex[:6]}"
            batch_commands = {
                cmd_key: [
                    'crm.deal.update',
                    {
                        'id': deal.bitrix_id,
                        'fields': update_data,
                    },
                ]
            }
            result = self.api.call_batch(batch_commands)
            
            if result:
                self.stats['updated_applications'] += 1
                # Обновляем локальную запись
                deal.last_sync = timezone.now()
                deal.save()
                
                # Создаем или обновляем запись AtlasApplication
                AtlasApplication.objects.update_or_create(
                    application_id=app_data.get('ID заявки из РР', f"atlas_{deal.bitrix_id}"),
                    defaults={
                        'full_name': self.get_full_name(app_data),
                        'phone': self.normalize_phone(app_data.get('Контактная информация (телефон)', '')),
                        'email': self.normalize_email(app_data.get('Email', '')),
                        'region': app_data.get('Регион', ''),
                        'deal': deal,
                        'raw_data': app_data,
                        'is_synced': True,
                        'last_sync': timezone.now()
                    }
                )
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении сделки {deal.bitrix_id}: {e}")
            raise
    
    def create_new_deal(self, app_data):
        """Создает новую сделку в Битрикс24"""
        try:
            # Подготавливаем данные для создания
            deal_data = self.prepare_deal_data(app_data, is_update=False)
            
            # Устанавливаем воронку
            deal_data['CATEGORY_ID'] = self.pipeline.bitrix_id
            
            # Устанавливаем источник "Атлас"
            deal_data['SOURCE_ID'] = '3'  # ID источника "Атлас"
            
            # Определяем этап
            stage_id = self.determine_stage(app_data)
            deal_data['STAGE_ID'] = stage_id
            
            # Создаем через API batch (одна команда)
            from uuid import uuid4
            cmd_key = f"add_{uuid4().hex[:6]}"
            batch_commands = {cmd_key: ['crm.deal.add', {'fields': deal_data}]}
            api_resp = self.api.call_batch(batch_commands)

            deal_id = None
            if isinstance(api_resp, dict):
                # Структура ответа fast_bitrix24.call_batch:
                # {
                #   'result': {
                #       cmd_key: <id> | True,
                #       'result_error': {...},
                #       ...
                #   },
                #   'time': {...}
                # }
                batch_res = api_resp.get('result', {})
                # Иногда вложено ещё одно 'result'
                if isinstance(batch_res, dict) and 'result' in batch_res:
                    batch_res = batch_res['result']
                if isinstance(batch_res, dict) and cmd_key in batch_res:
                    deal_id = batch_res[cmd_key]

            # Fallback: если не нашли по ключу, пробуем взять первый элемент результата
            if deal_id is None and isinstance(batch_res, dict) and batch_res:
                try:
                    deal_id = list(batch_res.values())[0]
                except Exception:
                    deal_id = None

            if deal_id is None:
                logger.error("Не удалось получить ID созданной сделки из batch-ответа: %s", api_resp)
                return

            self.stats['created_deals'] += 1

            # Создаем локальную запись
            deal = Deal.objects.create(
                bitrix_id=deal_id,
                title=deal_data.get('TITLE', ''),
                pipeline=self.pipeline,
                created_at=timezone.now(),
                last_sync=timezone.now()
            )

            # Создаем или обновляем запись AtlasApplication
            AtlasApplication.objects.update_or_create(
                application_id=app_data.get('ID заявки из РР', f"atlas_new_{deal_id}"),
                defaults={
                    'full_name': self.get_full_name(app_data),
                    'phone': self.normalize_phone(app_data.get('Контактная информация (телефон)', '')),
                    'email': self.normalize_email(app_data.get('Email', '')),
                    'region': app_data.get('Регион', ''),
                    'deal': deal,
                    'raw_data': app_data,
                    'is_synced': True,
                    'last_sync': timezone.now()
                }
            )
                
        except Exception as e:
            logger.error(f"Ошибка при создании сделки: {e}")
            raise
    
    def prepare_deal_data(self, app_data, is_update=False):
        """Подготавливает данные для создания/обновления сделки"""
        deal_data = {}
        
        # Проходим по маппингу полей
        for atlas_field, mapping in self.field_mapping['field_mapping'].items():
            if not isinstance(mapping, dict):
                continue
            bitrix_field = mapping['bitrix_field']
            field_type = mapping['type']
            
            # Обработка составных полей
            if field_type == 'composite' and 'source_fields' in mapping:
                # Составляем значение из нескольких полей
                if atlas_field == 'ФИО':
                    value = self.get_full_name(app_data)
                else:
                    # Общий случай для составных полей
                    parts = []
                    for source_field in mapping['source_fields']:
                        if source_field in app_data and app_data[source_field]:
                            parts.append(str(app_data[source_field]).strip())
                    value = ' '.join(parts)
                
                if mapping.get('normalize', False):
                    value = self.normalize_name(value)
            else:
                # Определяем из какого столбца брать данные (может быть source_field)
                src_col = mapping.get('source_field', atlas_field)

                raw_val = app_data.get(src_col)

                if not raw_val or (isinstance(raw_val, float) and pd.isna(raw_val)):
                    # Значение отсутствует – берём default_value или пропускаем
                    if 'default_value' in mapping:
                        value = mapping['default_value']
                    else:
                        continue
                else:
                    value = raw_val

                
                # Нормализация данных в зависимости от типа
                if field_type == 'phone' and mapping.get('normalize', False):
                    value = self.normalize_phone(value)
                    if value:
                        value = [{'VALUE': value, 'VALUE_TYPE': 'WORK'}]
                elif field_type == 'email' and mapping.get('normalize', False):
                    value = self.normalize_email(value)
                    if value:
                        value = [{'VALUE': value, 'VALUE_TYPE': 'WORK'}]
                elif field_type == 'string' and mapping.get('normalize', False):
                    value = self.normalize_name(value)
                elif field_type == 'select' and isinstance(mapping.get('options_mapping'), dict):
                    value = mapping['options_mapping'].get(value, value)
                elif field_type == 'datetime':
                    value = self.format_datetime(value)
                elif field_type == 'date':
                    value = self.format_date(value)
                
            if value:
                # Поддержка множественного назначения (один столбец → несколько полей Битрикс)
                if isinstance(bitrix_field, list):
                    for bf in bitrix_field:
                        deal_data[bf] = value
                else:
                    deal_data[bitrix_field] = value
        
        # Добавляем или обновляем TITLE: должно быть только ФИО без префикса
        if 'TITLE' not in deal_data:
            full_name = self.get_full_name(app_data) or 'Неизвестно'
            deal_data['TITLE'] = full_name
        else:
            # Если TITLE уже есть (например при обновлении), приводим к нужному формату
            existing_title = str(deal_data['TITLE']).strip()
            # Убираем потенциальный префикс "Заявка от "
            if existing_title.lower().startswith('заявка от '):
                deal_data['TITLE'] = existing_title[10:].strip()
        
        # Добавляем значения по умолчанию
        for field, mapping in self.field_mapping['field_mapping'].items():
            if 'default_value' in mapping and mapping['bitrix_field'] not in deal_data:
                deal_data[mapping['bitrix_field']] = mapping['default_value']

        # -- применяем правила на основе статусов (atlas / rr)
        self.apply_status_field_rules(deal_data, app_data)
        
        return deal_data

    # ------------------------------------------------------------------
    # Status-based field rules
    # ------------------------------------------------------------------
    def _get_status_order(self, name: str, source: str = 'atlas'):
        """Возвращает порядковый номер статуса по имени из кэша/БД."""
        if not name:
            return None
        cache = self._status_order_cache[source]
        if name in cache:
            return cache[name]
        from crm_connector.models import AtlasStatus, RRStatus
        Model = AtlasStatus if source == 'atlas' else RRStatus
        try:
            order_val = Model.objects.get(name=name).order
            cache[name] = order_val
            return order_val
        except Model.DoesNotExist:
            cache[name] = None
            return None

    def apply_status_field_rules(self, deal_data: dict, app_data: dict):
        """Применяет правила status_field_rules из JSON-маппинга."""
        rules_conf = self.field_mapping.get('status_field_rules', {})
        if not rules_conf:
            return

        atlas_status_name = str(app_data.get('Статус заявки в Атлас', '')).strip()
        rr_status_name = str(app_data.get('Статус заявки в РР', '')).strip()

        for field_code, cfg in rules_conf.items():
            if not isinstance(cfg, dict):
                continue
            source = cfg.get('source', 'atlas').lower()
            # Определяем текущий статус и его order
            current_status_name = atlas_status_name if source == 'atlas' else rr_status_name
            current_order = self._get_status_order(current_status_name, source)
            if current_order is None:
                continue

            ordered_rules = cfg.get('rules', [])
            # предполагаем, что rules перечислены в порядке возрастания; применяем последнее rule, чей order <= current_order
            selected_value = None
            for rule in ordered_rules:
                if not isinstance(rule, dict):
                    continue
                rule_status_name = rule.get('from')
                rule_order = self._get_status_order(rule_status_name, source)
                if rule_order is None:
                    continue
                if current_order >= rule_order:
                    selected_value = rule.get('value')
            if selected_value is not None:
                deal_data[field_code] = selected_value
    
    def determine_stage(self, app_data):
        """Определяет этап воронки для заявки на основе статусов"""
        rr_status = app_data.get('Статус заявки в РР', '').strip()
        atlas_status = app_data.get('Статус заявки в Атлас', '').strip()

        from crm_connector.utils import determine_stage_for_statuses
        return determine_stage_for_statuses(
            self.pipeline,
            atlas_status,
            rr_status,
            self.field_mapping,
        )
    
    def get_full_name(self, app_data):
        """Составляет полное имя из отдельных полей"""
        last_name = app_data.get('Фамилия', '').strip()
        first_name = app_data.get('Имя', '').strip()
        middle_name = app_data.get('Отчество', '').strip()
        
        parts = [last_name, first_name, middle_name]
        full_name = ' '.join(part for part in parts if part)
        
        return self.normalize_name(full_name)
    
    def normalize_name(self, name):
        """Нормализует ФИО для более точного сопоставления"""
        if not name:
            return ''
        
        # Убираем лишние пробелы и приводим к единому регистру
        name = ' '.join(name.strip().split()).title()
        
        # Исправляем распространенные ошибки в русских именах
        corrections = {
            # Варианты написания букв Ё/Е
            'Ё': 'Е', 'ё': 'е',
            
            # Варианты окончаний отчеств
            'Ичь': 'Ич', 'ичь': 'ич',
            'Ьевич': 'Евич', 'ьевич': 'евич',
            'Ьевна': 'Евна', 'ьевна': 'евна',
            
            # Исправление удвоенных букв
            'Лл': 'Л', 'лл': 'л',
            'Нн': 'Н', 'нн': 'н',
            'Мм': 'М', 'мм': 'м',
        }
        
        for old, new in corrections.items():
            name = name.replace(old, new)
        
        # Убираем точки в сокращениях (И. -> И)
        name = re.sub(r'\b([А-ЯЁ])\.', r'\1', name)
        
        # Стандартизируем дефисы в двойных фамилиях и именах
        name = re.sub(r'\s*[-–—]\s*', '-', name)
        
        # Убираем лишние пробелы после замен
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
    
    def normalize_phone(self, phone):
        """Нормализует телефон"""
        if not phone:
            return ''
        # Удаляем все символы кроме цифр
        phone = re.sub(r'[^\d]', '', str(phone))
        # Приводим к единому формату
        if len(phone) == 11 and phone.startswith('8'):
            phone = '7' + phone[1:]
        elif len(phone) == 10:
            phone = '7' + phone
        return phone
    
    def normalize_email(self, email):
        """Нормализует email"""
        if not email:
            return ''
        return str(email).lower().strip()
    
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
    
    def extract_phone_from_deal(self, deal_details):
        """Извлекает телефон из данных сделки"""
        if not deal_details:
            return ''
        phone = deal_details.get('PHONE')
        if phone and isinstance(phone, list) and len(phone) > 0:
            return phone[0].get('VALUE', '')
        return ''
    
    def extract_email_from_deal(self, deal_details):
        """Извлекает email из данных сделки"""
        if not deal_details:
            return ''
        email = deal_details.get('EMAIL')
        if email and isinstance(email, list) and len(email) > 0:
            return email[0].get('VALUE', '')
        return ''
    
    def extract_snils_from_deal(self, deal_details):
        """Извлекает СНИЛС из данных сделки"""
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
    
    def _get_or_create_stage(self, stage_id):
        """Получает или создает этап"""
        if not stage_id:
            return None
        
        try:
            return Stage.objects.get(bitrix_id=stage_id)
        except Stage.DoesNotExist:
            # Создаем базовый этап
            return Stage.objects.create(
                bitrix_id=stage_id,
                name=stage_id,
                pipeline=self.pipeline
            )
    
    def _parse_datetime(self, date_str):
        """Парсит дату из строки Битрикс24"""
        if not date_str:
            return None
        
        try:
            # Битрикс24 возвращает даты в формате ISO
            return timezone.make_aware(
                datetime.fromisoformat(date_str.replace('T', ' ').split('+')[0])
            )
        except:
            return None
    
    def format_datetime(self, value):
        """Форматирует дату и время для отправки в Битрикс24"""
        if isinstance(value, str):
            try:
                # Пытаемся парсить различные форматы
                if ' ' in value:
                    # Формат с временем: "18.06.2025 23:50:05"
                    dt = datetime.strptime(value, '%d.%m.%Y %H:%M:%S')
                    return dt.strftime('%Y-%m-%dT%H:%M:%S')
                else:
                    # Только дата
                    dt = datetime.strptime(value, '%d.%m.%Y')
                    return dt.strftime('%Y-%m-%d')
            except:
                return value
        elif isinstance(value, datetime):
            return value.strftime('%Y-%m-%dT%H:%M:%S')
        return value
    
    def format_date(self, value):
        """Форматирует дату для отправки в Битрикс24"""
        if isinstance(value, str):
            try:
                # Парсим формат "dd.mm.yyyy"
                dt = datetime.strptime(value, '%d.%m.%Y')
                return dt.strftime('%Y-%m-%d')
            except:
                try:
                    # Пробуем другой формат
                    dt = datetime.strptime(value, '%Y-%m-%d')
                    return dt.strftime('%Y-%m-%d')
                except:
                    return value
        elif isinstance(value, datetime):
            return value.strftime('%Y-%m-%d')
        return value
    
    def print_statistics(self):
        """Выводит статистику импорта"""
        self.stdout.write("\n" + "="*50)
        self.stdout.write("СТАТИСТИКА ИМПОРТА:")
        self.stdout.write(f"Обновлено сделок из Битрикс24: {self.stats['updated_deals']}")
        self.stdout.write(f"Удалено отсутствующих сделок: {self.stats['deleted_deals']}")
        self.stdout.write(f"Удалено дублированных сделок: {self.stats['duplicate_deals_removed']}")
        self.stdout.write(f"Найдено совпадений с заявками: {self.stats['matched_applications']}")
        self.stdout.write(f"Новых заявок без совпадений: {self.stats['new_applications']}")
        self.stdout.write(f"Обновлено существующих сделок: {self.stats['updated_applications']}")
        self.stdout.write(f"Создано новых сделок: {self.stats['created_deals']}")
        self.stdout.write(f"Ошибок: {self.stats['errors']}")
        self.stdout.write("="*50 + "\n") 

    # ------------------------------------------------------------------
    #  Helper: оставляем актуальную заявку на основании номера заявления РР
    # ------------------------------------------------------------------

    def _filter_actual_applications(self, applications):
        """Возвращает список заявок, в котором для каждого СНИЛС остаётся
        только самая «свежая» (c наибольшим номером заявления на РР).

        Правило определения свежести:
          • поле «Номер заявления на РР» имеет вид ХХХ-...-0001, 0002 и т.д.;
          • чем больше число после последнего дефиса, тем заявка новее.
        """

        def parse_app_number(raw: str) -> int:
            if not raw:
                return 0
            raw = str(raw).strip()
            # Берём цифры после последнего дефиса
            m = re.search(r"-(\d+)$", raw)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    return 0
            return 0

        by_snils = {}
        for app in applications:
            snils_raw = str(app.get('СНИЛС', '') or '').replace(' ', '').strip()
            if not snils_raw:
                # Нет СНИЛС – добавляем как есть (будет обработана отдельно)
                key = f"nosnils_{id(app)}"
                by_snils[key] = app
                continue

            current = by_snils.get(snils_raw)
            if current is None:
                by_snils[snils_raw] = app
            else:
                # Сравниваем номера заявлений
                cur_num = parse_app_number(current.get('Номер заявления на РР', ''))
                new_num = parse_app_number(app.get('Номер заявления на РР', ''))
                if new_num >= cur_num:
                    by_snils[snils_raw] = app

        filtered = list(by_snils.values())
        diff = len(applications) - len(filtered)
        if diff > 0:
            self.stdout.write(f"Отфильтровано {diff} неактуальных заявок (дубликаты по СНИЛС)")
        return filtered 