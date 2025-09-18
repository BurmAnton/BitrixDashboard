import requests
from django.conf import settings
from .models import Pipeline, Stage
from fast_bitrix24 import Bitrix
import logging

# Добавляем определение логгера
logger = logging.getLogger(__name__)

class Bitrix24API:
    """Класс для работы с API Битрикс24 через библиотеку fast_bitrix24 с настройками из .env"""
    
    def __init__(self):
        self.domain = settings.BITRIX24_SETTINGS['DOMAIN']
        self.webhook_code = settings.BITRIX24_SETTINGS['CLIENT_SECRET']
        
        # Очищаем домен от протокола и завершающих слешей
        domain = self.domain.replace('https://', '').replace('http://', '').strip('/')
        
        # Формат вебхука: https://domain.bitrix24.ru/rest/1/webhook_code/
        webhook_url = f"https://{domain}/rest/1/{self.webhook_code}/"
        
        self.bitrix = Bitrix(webhook_url)
        print(f"Инициализирован клиент Битрикс24 с вебхуком: {webhook_url}")
    
    def call_method(self, method, params=None):
        """Вызывает метод API Битрикс24 с помощью fast_bitrix24"""
        if params is None:
            params = {}
        print(params)
        if method in ("crm.deal.add", "crm.deal.update") and isinstance(params, dict) and "fields" in params:        
            try:
                debug_fields = {
                    k: params["fields"].get(k)
                    for k in params["fields"].keys()
                    if k.startswith("UF_CRM") or k == "TITLE"
                }
                logger.info("➡️ %s → передаём поля: %s", method, debug_fields)
            except Exception:
                logger.info("❌ Ошибка при отладке полей")

        try:
            # Для методов list используем get_all
            if method.endswith('.list') or method.endswith('.getlist') or method.endswith('.fields'):
                result = self.bitrix.get_all(method, params)
            else:
                result = self.bitrix.call(method, params)
            
            # Добавляем отладочную информацию
            logger.debug(f"API метод {method} вернул результат типа {type(result)}")
            
            return {'result': result}
        except Exception as e:
            logger.error(f"❌ Ошибка при вызове метода {method}: {str(e)}")
            # Для отладки
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error(f"Ответ API: {e.response.text}")
            raise

    # ------------------------------------------------------------------
    # Batch wrapper for create/update operations
    # ------------------------------------------------------------------
    def call_batch(self, commands: dict, halt: bool = False):
        """Вызывает пакет методов через fast_bitrix24.call_batch.

        Параметр *commands* должен быть словарём вида
            {
                'cmd_name': ['crm.deal.add', {'fields': {...}}],
                ...
            }

        По умолчанию *halt* = False, чтобы при ошибке выполнения одной
        команды остальные продолжали исполняться (аналогично &halt=0 в REST).
        Возвращает словарь ответа сервера без изменений.
        """
        try:
            cmd_count = len(commands)
            logger.debug("➡️ call_batch: %s команд, halt=%s", cmd_count, halt)

            # ------------------------------------------------------------------
            # Оптимизация: если передана всего одна команда, смысла тащить
            # полноценный batch-вызов нет – вызываем метод напрямую через
            # call_method() и затем эмулируем формат ответа batch для
            # дальнейшего совместимого разбора.
            # ------------------------------------------------------------------
            if cmd_count == 1:
                alias, cmd = next(iter(commands.items()))
                if isinstance(cmd, (list, tuple)) and len(cmd) == 2:
                    method, params = cmd
                    single_res = self.call_method(method, params)
                    emulated = {
                        'result': {
                            alias: single_res,
                            'result_error': {},
                        },
                        'time': {},
                    }
                    logger.debug("⬅️ call_batch(single): эмулированный ответ %s", emulated)
                    return emulated

            # ------------------------------------------------------------------
            # Обычный сценарий: несколько команд → передаём в batch
            # ------------------------------------------------------------------
            payload = {
                'halt': 0 if not halt else 1,
                'cmd': commands,
            }

            result = self.bitrix.call_batch(payload)

            # Распечатываем ошибки, если они есть
            if isinstance(result, dict):
                inner = result.get('result', {}) if 'result' in result else {}
                err_dict = inner.get('result_error') or inner.get('result_errorfull')
                if err_dict:
                    logger.error("❗ Ошибки batch: %s", err_dict)
                logger.debug("⬅️ call_batch: ключи результата: %s", list(result.keys()))
            else:
                logger.debug("⬅️ call_batch: получен ответ типа %s (размер %s)", type(result).__name__, len(result))

            return result
        except Exception as e:
            logger.error("❌ Ошибка при call_batch: %s", str(e))
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error("Ответ API: %s", e.response.text)
            raise

    # ------------------------------------------------------------------
    # Обертка для fast_bitrix24.get_all (нужна для обратной совместимости)
    # ------------------------------------------------------------------
    def get_all(self, method: str, params=None):
        """Возвращает все элементы ответа списочных методов Битрикс24.

        В кодовой базе уже используются вызовы `api.get_all(...)`. Чтобы не
        менять множество мест, добавляем эту обертку, которая просто
        проксирует вызов к `self.bitrix.get_all` и возвращает сырые данные.
        """
        if params is None:
            params = {}

        try:
            result = self.bitrix.get_all(method, params)
            logger.debug(
                "get_all: метод %s, получено элементов: %s",
                method,
                len(result) if isinstance(result, (list, tuple)) else 'n/a',
            )
            return result
        except Exception as e:
            logger.error("❌ Ошибка при get_all %s: %s", method, str(e))
            # Добавляем вывод тела ответа при наличии
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error("Ответ API: %s", e.response.text)
            raise
    
    def get_pipelines(self):
        """Получает список воронок продаж из Битрикс24"""
        try:
            # Получаем имя для основной воронки из настроек компании
            try:
                company_info = self.bitrix.call('crm.company.settings.fields')
                main_pipeline_name = 'Стандартная воронка продаж'
                if company_info and isinstance(company_info, dict):
                    # Пытаемся получить название из настроек
                    main_pipeline_name = company_info.get('COMPANY_NAME', 'Стандартная воронка продаж')
            except Exception as e:
                print(f"❌ Не удалось получить название компании: {str(e)}")
                main_pipeline_name = 'Стандартная воронка продаж'
            
            # Используем специальный метод для воронок сделок
            pipelines_data = self.bitrix.get_all('crm.dealcategory.list')
            
            if pipelines_data is None:
                print("❌ API вернул None вместо списка воронок")
                return {}
            
            # Создаем словарь воронок
            pipelines = {}
            
            # Добавляем основную воронку (с ID=0), которая всегда присутствует
            pipelines['0'] = {
                'id': '0',
                'name': 'Заявки (граждане)',
                'sort': 100,
                'is_active': True,
                'is_main': True,
                'stages': []
            }
            
            # Добавляем дополнительные воронки
            for pipeline in pipelines_data:
                pipeline_id = str(pipeline.get('ID'))
                if pipeline_id:
                    pipelines[pipeline_id] = {
                        'id': pipeline_id,
                        'name': pipeline.get('NAME', f'Воронка {pipeline_id}'),
                        'sort': int(pipeline.get('SORT', 500)),
                        'is_active': pipeline.get('IS_LOCKED', 'N') != 'Y',
                        'is_main': False,  # Дополнительные воронки не основные
                        'stages': []
                    }
            
            # Для каждой воронки получаем этапы
            for pipeline_id in pipelines.keys():
                stages = self._get_pipeline_stages(pipeline_id)
                pipelines[pipeline_id]['stages'] = stages
            
            return pipelines
        except Exception as e:
            print(f"❌ Ошибка при получении воронок продаж: {str(e)}")
            return {}
    
    def _get_pipeline_stages(self, pipeline_id):
        """Получает этапы для конкретной воронки"""
        try:
            # Для воронок получаем их стадии через специальный метод
            stages_data = self.bitrix.get_all('crm.dealcategory.stage.list', {
                'id': pipeline_id
            })
            
            stages = []
            
            # Если не смогли получить стадии через специальный метод, используем общий
            if not stages_data:
                # Получаем все статусы сделок
                statuses = self.bitrix.call('crm.status.list', {
                    'filter': {'ENTITY_ID': 'DEAL_STAGE'}
                })
                
                for status in statuses:
                    # Фильтруем только стадии нужной воронки
                    if status.get('CATEGORY_ID') == pipeline_id:
                        stages.append({
                            'id': status['STATUS_ID'],
                            'name': status['NAME'],
                            'sort': int(status.get('SORT', '500')),
                            # Не определяем тип и вероятность
                        })
            
            return stages
                
        except Exception as e:
            print(f"❌ Ошибка при получении этапов для воронки {pipeline_id}: {str(e)}")
            return []
    
    def sync_pipelines_and_stages(self):
        """Синхронизирует воронки и их этапы с Битрикс24"""
        try:
            from django.utils import timezone
            from .models import Pipeline, Stage
            
            # Получаем данные из Битрикс24
            bitrix_data = self.get_pipelines()
            
            if not bitrix_data:
                print("❌ Не удалось получить данные о воронках из Битрикс24")
                return {
                    'success': False,
                    'pipelines_count': 0,
                    'stages_count': 0,
                }
            
            # Текущее время для отметки синхронизации
            current_time = timezone.now()
            
            # Счетчики для статистики
            pipelines_count = 0
            stages_count = 0
            
            # Синхронизируем воронки
            for pipeline_id, pipeline_data in bitrix_data.items():
                pipeline, created = Pipeline.objects.update_or_create(
                    bitrix_id=pipeline_id,
                    defaults={
                        'name': pipeline_data['name'],
                        'sort': pipeline_data['sort'],
                        'is_active': pipeline_data['is_active'],
                        'is_main': pipeline_data['is_main'],
                        'last_sync': current_time
                    }
                )
                
                pipelines_count += 1
                
                # Синхронизируем этапы воронки
                for stage_data in pipeline_data['stages']:
                    stage, created = Stage.objects.update_or_create(
                        bitrix_id=stage_data['id'],
                        defaults={
                            'pipeline': pipeline,
                            'name': stage_data['name'],
                            'sort': stage_data['sort'],
                            # Не обновляем тип стадии при синхронизации
                            # Он должен настраиваться пользователем в админке
                        }
                    )
                    
                    stages_count += 1
            
            print(f"✅ Успешно синхронизировано {pipelines_count} воронок и {stages_count} этапов")
            
            return {
                'success': True,
                'pipelines_count': pipelines_count,
                'stages_count': stages_count,
            }
            
        except Exception as e:
            print(f"❌ Ошибка при синхронизации воронок: {str(e)}")
            import traceback
            print(traceback.format_exc())
            
            return {
                'success': False,
                'error': str(e),
                'pipelines_count': 0,
                'stages_count': 0,
            }

    def test_api_connection(self):
        """Проверяет соединение с API Битрикс24"""
        print(f"Проверка подключения к домену: {self.domain}")
        
        # Пробуем получить самые базовые данные
        try:
            # Пробуем получить воронки (более надежно в новых версиях Битрикс24)
            pipelines = self.bitrix.call('crm.dealcategory.list')
            if pipelines is not None:
                print(f"✅ Подключение успешно! Получены воронки: {len(pipelines)}")
                return True
        except Exception as e:
            print(f"❌ Ошибка при проверке через crm.dealcategory.list: {str(e)}")
            # Дополнительная информация для отладки
            print(f"Тип ошибки: {type(e)}")
            
            try:
                # Пробуем получить статусы сделок (должно сработать даже на старых версиях Битрикс24)
                statuses = self.bitrix.call('crm.status.list', {
                    'filter': {'ENTITY_ID': 'DEAL_STAGE'}
                })
                if statuses:
                    print(f"✅ Подключение успешно! Получены статусы сделок: {len(statuses)}")
                    return True
            except Exception as e2:
                print(f"❌ Ошибка при проверке через crm.status.list: {str(e2)}")
                
                try:
                    # Альтернативный метод - получение полей сделки
                    fields = self.bitrix.call('crm.deal.fields')
                    if fields:
                        print(f"✅ Подключение успешно! Получены поля сделки")
                        return True
                except Exception as e3:
                    print(f"❌ Ошибка при проверке через crm.deal.fields: {str(e3)}")
                
                # Прямой запрос через requests для проверки вебхука
                try:
                    webhook_url = f"https://{self.domain}/rest/1/{self.webhook_code}/profile/"
                    response = requests.get(webhook_url)
                    if response.status_code == 200:
                        print(f"✅ Подключение через прямой запрос успешно!")
                        return True
                except Exception as e4:
                    print(f"❌ Ошибка при прямом запросе: {str(e4)}")
        
        print("❌ Все методы проверки подключения не удались")
        return False 

    def check_pipelines_freshness(self):
        """Проверяет актуальность данных воронок в базе данных"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Получаем время последней синхронизации
        latest_pipeline = Pipeline.objects.order_by('-last_sync').first()
        
        if not latest_pipeline or not latest_pipeline.last_sync:
            return {
                'is_fresh': False,
                'message': 'Данные воронок никогда не синхронизировались',
                'last_sync': None
            }
        
        # Проверяем, насколько свежие данные (например, не старше 6 часов)
        max_age = timedelta(hours=6)
        is_fresh = (timezone.now() - latest_pipeline.last_sync) <= max_age
        
        return {
            'is_fresh': is_fresh,
            'message': 'Данные актуальны' if is_fresh else 'Данные устарели',
            'last_sync': latest_pipeline.last_sync,
            'age_hours': (timezone.now() - latest_pipeline.last_sync).total_seconds() / 3600
        } 

    def verify_pipelines_data(self):
        """Проверяет соответствие данных в БД и в Битрикс24"""
        # Получаем данные из Битрикс24
        bitrix_pipelines = self.get_pipelines()
        
        # Получаем данные из БД
        db_pipelines = {p.bitrix_id: p for p in Pipeline.objects.all()}
        
        differences = {
            'missing_in_db': [],
            'missing_in_bitrix': [],
            'different_names': [],
            'total_in_bitrix': len(bitrix_pipelines),
            'total_in_db': len(db_pipelines),
            'is_identical': True
        }
        
        # Проверяем пропущенные в БД
        for b_id, b_data in bitrix_pipelines.items():
            if b_id not in db_pipelines:
                differences['missing_in_db'].append(b_id)
                differences['is_identical'] = False
            elif b_data['name'] != db_pipelines[b_id].name:
                differences['different_names'].append({
                    'id': b_id,
                    'bitrix_name': b_data['name'],
                    'db_name': db_pipelines[b_id].name
                })
                differences['is_identical'] = False
        
        # Проверяем лишние в БД
        for db_id in db_pipelines:
            if db_id not in bitrix_pipelines:
                differences['missing_in_bitrix'].append(db_id)
                differences['is_identical'] = False
        
        return differences 

    def get_all_deals(self):
        """Получает все сделки из Битрикс24"""
        try:
            # Явно указываем, что хотим все сделки без ограничений
            deals = self.bitrix.get_all('crm.deal.list', {
                'select': ['*', 'UF_*'],
                'filter': {}  # Пустой фильтр для явного указания, что мы хотим все сделки
            })
            
            if deals is None:
                print("⚠️ API вернул None вместо списка сделок")
                return []
            
            print(f"✅ Получено {len(deals)} сделок из Битрикс24")
            
            # Сортировка на стороне Python
            if deals:
                from datetime import datetime
                try:
                    deals.sort(key=lambda deal: datetime.strptime(deal.get('DATE_CREATE', '2000-01-01T00:00:00+0000'), 
                                                            '%Y-%m-%dT%H:%M:%S%z'), 
                              reverse=True)  # DESC сортировка
                except Exception as sort_error:
                    print(f"⚠️ Предупреждение при сортировке сделок: {str(sort_error)}")
            
            return deals
        except Exception as e:
            print(f"❌ Ошибка при получении сделок: {str(e)}")
            import traceback
            print(f"Детали ошибки: {traceback.format_exc()}")
            return []

    def get_deals_by_pipeline(self, pipeline_id):
        """Получает сделки из указанной воронки"""
        try:
            deals = self.bitrix.get_all('crm.deal.list', {
                'select': ['*', 'UF_*'],
                'filter': {'CATEGORY_ID': pipeline_id}
            })
            return deals
        except Exception as e:
            print(f"❌ Ошибка при получении сделок для воронки {pipeline_id}: {str(e)}")
            return []

    def get_deals_by_date(self, start_date):
        """Получает сделки, созданные после указанной даты"""
        try:
            # Конвертируем дату в строку в формате Битрикс24
            date_str = start_date.strftime('%Y-%m-%dT%H:%M:%S')
            deals = self.bitrix.get_all('crm.deal.list', {
                'select': ['*', 'UF_*'],
                'filter': {'>DATE_CREATE': date_str}
            })
            return deals
        except Exception as e:
            print(f"❌ Ошибка при получении сделок с {start_date}: {str(e)}")
            return []

    def get_deal_fields(self):
        """Получает метаданные полей сделки"""
        try:
            fields = self.bitrix.call('crm.deal.fields')
            return fields
        except Exception as e:
            print(f"❌ Ошибка при получении полей сделки: {str(e)}")
            return {} 
        
    def get_deal_field_list(self, ChoosenField):
        """Получает лист 'items' у поля сделки."""
        try:
            fields = self.bitrix.get_all('crm.deal.fields')
            items = fields[f"{ChoosenField}"].get("items",[])
            fields = [(item["ID"],item["VALUE"]) for item in items]
            return fields
        except Exception as e:
            print(f"❌ Ошибка при получении полей сделки: {str(e)}")
            return {} 

    def find_contact_by_email(self, email):
        """Находит контакт по email"""
        try:
            contacts = self.bitrix.call('crm.contact.list', {
                'filter': { 'EMAIL': email }
            })
            return contacts
        except Exception as e:
            logger.error(f"Ошибка при поиске контакта по email: {str(e)}")
            return []

    def find_contact_by_phone(self, phone):
        """Находит контакт по телефону"""
        try:
            contacts = self.bitrix.call('crm.contact.list', {
                'filter': { 'PHONE': phone }
            })
            return contacts
        except Exception as e:
            logger.error(f"Ошибка при поиске контакта по телефону: {str(e)}")
            return []

    def add_contact(self, contact_data):
        """Добавляет новый контакт"""
        try:
            result = self.bitrix.call('crm.contact.add', {
                'fields': contact_data
            })
            return result
        except Exception as e:
            logger.error(f"Ошибка при добавлении контакта: {str(e)}")
            raise

    def update_contact(self, contact_id, contact_data):
        """Обновляет существующий контакт"""
        try:
            result = self.bitrix.call('crm.contact.update', {
                'id': contact_id,
                'fields': contact_data
            })
            return result
        except Exception as e:
            logger.error(f"Ошибка при обновлении контакта: {str(e)}")
            raise

    def find_company_by_name(self, company_name):
        """Находит компанию по названию"""
        try:
            companies = self.bitrix.call('crm.company.list', {
                'filter': { 'TITLE': company_name }
            })
            return companies
        except Exception as e:
            logger.error(f"Ошибка при поиске компании по названию: {str(e)}")
            return []

    def add_company(self, company_data):
        """Добавляет новую компанию"""
        try:
            result = self.bitrix.call('crm.company.add', {
                'fields': company_data
            })
            return result
        except Exception as e:
            logger.error(f"Ошибка при добавлении компании: {str(e)}")
            raise

    def update_company(self, company_id, company_data):
        """Обновляет существующую компанию"""
        try:
            result = self.bitrix.call('crm.company.update', {
                'id': company_id,
                'fields': company_data
            })
            return result
        except Exception as e:
            logger.error(f"Ошибка при обновлении компании: {str(e)}")
            raise

    def add_deal(self, deal_data):
        """Добавляет новую сделку"""
        try:
            result = self.bitrix.call('crm.deal.add', {
                'fields': deal_data
            })
            return result
        except Exception as e:
            logger.error(f"Ошибка при добавлении сделки: {str(e)}")
            raise

    def get_company_industries(self):
        """Получает список доступных отраслей (сфер деятельности) для компаний"""
        try:
            # Используем более надежный способ получения данных
            result = self.bitrix.call('crm.company.fields')
            if isinstance(result, dict) and 'INDUSTRY' in result and 'items' in result['INDUSTRY']:
                # Преобразуем в формат [(id, name), ...]
                return [(item['ID'], item['VALUE']) for item in result['INDUSTRY']['items']]
            else:
                # Альтернативный способ получения отраслей через справочник
                try:
                    industries = self.bitrix.call('crm.enum.industry')
                    if isinstance(industries, list):
                        return [(item['ID'], item['VALUE']) for item in industries]
                except:
                    pass
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении списка отраслей: {str(e)}")
            return []

    def get_company_types(self):
        """Получает список доступных типов компаний"""
        try:
            # Используем более надежный способ получения данных
            result = self.bitrix.call('crm.company.fields')
            if isinstance(result, dict) and 'COMPANY_TYPE' in result and 'items' in result['COMPANY_TYPE']:
                # Преобразуем в формат [(id, name), ...]
                return [(item['ID'], item['VALUE']) for item in result['COMPANY_TYPE']['items']]
            else:
                # Альтернативный способ получения типов компаний через справочник
                try:
                    types = self.bitrix.call('crm.enum.ownertype')
                    if isinstance(types, list):
                        return [(item['ID'], item['VALUE']) for item in types]
                except:
                    pass
            return []
        except Exception as e:
            logger.error(f"Ошибка при получении списка типов компаний: {str(e)}")
            return []

    def get_pipeline_stages(self, pipeline_id):
        """Получает список стадий указанной воронки по её Bitrix ID"""
        try:
            # Используем правильный метод API для получения стадий воронки
            statuses = self.bitrix.call('crm.status.list', {
                'filter': {'ENTITY_ID': f'DEAL_STAGE_{pipeline_id}'}
            })
            
            if isinstance(statuses, list) and statuses:
                # Формируем список стадий в формате [(id, name), ...]
                stages = []
                for status in statuses:
                    if isinstance(status, dict) and 'STATUS_ID' in status and 'NAME' in status:
                        stages.append((status['STATUS_ID'], status['NAME']))
                return stages
            
            # Если не получилось, пробуем альтернативный метод
            try:
                result = self.bitrix.call('crm.dealcategory.stage.list', {
                    'id': str(pipeline_id)
                })
                
                if isinstance(result, list):
                    return [(stage['STATUS_ID'], stage['NAME']) for stage in result if isinstance(stage, dict)]
            except:
                pass
            
            # Если все методы не сработали, вернем стандартные стадии
            return [
                ('C11:NEW', 'Первичный контакт'),
                ('C11:PREPARATION', 'Переговоры'),
                ('C11:EXECUTING', 'Составление списков'),
                ('C11:FINAL_INVOICE', 'Согласование списков'),
                ('C11:WON', 'Списки согласованы'),
                ('C11:LOSE', 'Сделка отменена')
            ]
        except Exception as e:
            logger.error(f"Ошибка при получении стадий воронки {pipeline_id}: {str(e)}")
            # В случае ошибки вернем стандартные стадии
            return [
                ('C11:NEW', 'Первичный контакт'),
                ('C11:PREPARATION', 'Переговоры'),
                ('C11:EXECUTING', 'Составление списков'),
                ('C11:FINAL_INVOICE', 'Согласование списков'),
                ('C11:WON', 'Списки согласованы'),
                ('C11:LOSE', 'Сделка отменена')
            ] 