import hashlib
import json
import os
import logging
from functools import wraps
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class AtlasDataCache:
    """Кеш для данных заявок из Атласа"""

    CACHE_PREFIX = "atlas_data:"
    CACHE_TIMEOUT = 7200  # 2 часа по умолчанию
    CACHE_TIMEOUT_SHORT = 1800  # 30 минут для часто обновляемых данных
    CACHE_TIMEOUT_LONG = 21600  # 6 часов для редко обновляемых данных

    # Ключи для промежуточных данных
    ATLAS_APPS_KEY = CACHE_PREFIX + "atlas_apps"
    DEALS_KEY = CACHE_PREFIX + "deals"
    PIPELINE_KEY = CACHE_PREFIX + "pipeline"
    ATLAS_STATUSES_KEY = CACHE_PREFIX + "atlas_statuses"
    QUOTA_DATA_KEY = CACHE_PREFIX + "quota_data:"  # + quota_id

    @staticmethod
    def get_cache():
        """Получает экземпляр кеша (Django cache с поддержкой сериализации)"""
        # Используем Django cache который уже настроен с PickleSerializer в settings.py
        # Это автоматически обрабатывает сериализацию Django объектов
        return cache

    @staticmethod
    def make_key(func_name, args, kwargs):
        """Создает ключ кеша на основе имени функции и аргументов"""
        # Нормализуем аргументы для более эффективного кеширования
        normalized_args = []
        for arg in args:
            if hasattr(arg, 'id'):  # Django model object
                normalized_args.append(('model', arg.__class__.__name__, arg.id))
            elif hasattr(arg, '__dict__'):  # Complex object
                normalized_args.append(('obj', str(arg)))
            else:
                normalized_args.append(arg)

        normalized_kwargs = {}
        for k, v in kwargs.items():
            if hasattr(v, 'id'):  # Django model object
                normalized_kwargs[k] = ('model', v.__class__.__name__, v.id)
            elif hasattr(v, '__dict__'):  # Complex object
                normalized_kwargs[k] = ('obj', str(v))
            else:
                normalized_kwargs[k] = v

        key_data = {
            'func': func_name,
            'args': normalized_args,
            'kwargs': normalized_kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return AtlasDataCache.CACHE_PREFIX + hashlib.md5(key_str.encode()).hexdigest()

    @staticmethod
    def clear_cache():
        """Очищает весь кеш данных Атласа"""
        try:
            cache_instance = AtlasDataCache.get_cache()
            if hasattr(cache_instance, 'delete_pattern'):
                # Redis
                deleted_count = cache_instance.delete_pattern(AtlasDataCache.CACHE_PREFIX + "*")
                logger.info(f"Cleared Redis cache for Atlas data - deleted {deleted_count} keys")
            else:
                # Django cache - не поддерживает паттерны, так что очищаем весь кеш
                cache_instance.clear()
                logger.info("Cleared Django cache (full clear) for Atlas data")
        except Exception as e:
            logger.error(f"Error clearing Atlas cache: {e}")

    @staticmethod
    def get_cached_atlas_data():
        """Получает кешированные данные заявок и сделок из Атласа"""
        cache_instance = AtlasDataCache.get_cache()

        try:
            # Получаем pipeline
            pipeline = cache_instance.get(AtlasDataCache.PIPELINE_KEY)
            if not pipeline:
                from crm_connector.models import Pipeline
                pipeline = Pipeline.objects.filter(name='Заявки (граждане)').first()
                if pipeline:
                    cache_instance.set(AtlasDataCache.PIPELINE_KEY, pipeline, AtlasDataCache.CACHE_TIMEOUT)
                    logger.info("Cached pipeline object")
                else:
                    logger.warning("Pipeline 'Заявки (граждане)' not found")
                    return None, None, None

            # Получаем заявки
            atlas_apps = cache_instance.get(AtlasDataCache.ATLAS_APPS_KEY)
            if atlas_apps is None:
                from crm_connector.models import AtlasApplication
                atlas_apps_queryset = AtlasApplication.objects.select_related('deal').filter(deal__pipeline=pipeline)
                # Конвертируем в список для сериализации
                atlas_apps = list(atlas_apps_queryset)
                cache_instance.set(AtlasDataCache.ATLAS_APPS_KEY, atlas_apps, AtlasDataCache.CACHE_TIMEOUT)
                logger.info(f"Cached {len(atlas_apps)} atlas applications")

            # Получаем сделки
            deals = cache_instance.get(AtlasDataCache.DEALS_KEY)
            if deals is None:
                from crm_connector.models import Deal
                deals_queryset = Deal.objects.select_related('stage').filter(pipeline=pipeline)
                deals = list(deals_queryset)
                cache_instance.set(AtlasDataCache.DEALS_KEY, deals, AtlasDataCache.CACHE_TIMEOUT)
                logger.info(f"Cached {len(deals)} deals")

            return pipeline, atlas_apps, deals

        except Exception as e:
            logger.error(f"Error getting cached Atlas data: {e}")
            return None, None, None
    
    @staticmethod
    def get_cached_atlas_statuses():
        """Получает кешированные статусы Атлас"""
        cache_instance = AtlasDataCache.get_cache()
        
        try:
            statuses = cache_instance.get(AtlasDataCache.ATLAS_STATUSES_KEY)
            if statuses is None:
                from crm_connector.models import AtlasStatus
                statuses = {status.name: status.order for status in AtlasStatus.objects.all()}
                cache_instance.set(AtlasDataCache.ATLAS_STATUSES_KEY, statuses, AtlasDataCache.CACHE_TIMEOUT_LONG)
                logger.info(f"Cached {len(statuses)} Atlas statuses")
            return statuses
        except Exception as e:
            logger.error(f"Error getting cached Atlas statuses: {e}")
            return {}
    
    @staticmethod
    def invalidate_specific_keys(keys_to_invalidate):
        """Очищает конкретные ключи кеша"""
        try:
            cache_instance = AtlasDataCache.get_cache()
            for key in keys_to_invalidate:
                cache_instance.delete(key)
                logger.info(f"Invalidated cache key: {key}")
        except Exception as e:
            logger.error(f"Error invalidating specific cache keys: {e}")
    
    @staticmethod
    def warm_up_cache():
        """Предварительная загрузка важных данных в кеш"""
        try:
            logger.info("Начинаем предварительную загрузку кеша...")
            # Загружаем данные Atlas
            AtlasDataCache.get_cached_atlas_data()
            # Загружаем статусы
            AtlasDataCache.get_cached_atlas_statuses()
            logger.info("Предварительная загрузка кеша завершена")
        except Exception as e:
            logger.error(f"Error warming up cache: {e}")


def cache_atlas_data(timeout=None):
    """
    Декоратор для кеширования функций, работающих с данными Атласа

    Args:
        timeout: Время жизни кеша в секундах (по умолчанию 1 час)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            start_time = time.time()

            cache_key = AtlasDataCache.make_key(func.__name__, args, kwargs)
            cache_instance = AtlasDataCache.get_cache()
            cache_timeout = timeout or AtlasDataCache.CACHE_TIMEOUT

            try:
                # Пробуем получить данные из кеша
                cached_result = cache_instance.get(cache_key)
                if cached_result is not None:
                    cache_time = time.time() - start_time
                    logger.info(f"Cache HIT for {func.__name__} - key: {cache_key[:32]}... - time: {cache_time:.3f}s")
                    return cached_result
            except Exception as e:
                logger.warning(f"Cache read error for {func.__name__}: {e}")

            # Выполняем функцию
            logger.info(f"Cache MISS for {func.__name__} - executing function")
            result = func(*args, **kwargs)

            # Сохраняем результат в кеш
            try:
                cache_instance.set(cache_key, result, cache_timeout)
                execution_time = time.time() - start_time
                logger.info(f"Cached result for {func.__name__} - key: {cache_key[:32]}... - time: {execution_time:.3f}s")
            except Exception as e:
                logger.warning(f"Cache write error for {func.__name__}: {e}")

            return result

        return wrapper
    return decorator


def invalidate_atlas_cache():
    """Декоратор для инвалидации кеша после выполнения функции"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            # Очищаем кеш после выполнения функции
            AtlasDataCache.clear_cache()
            return result

        return wrapper
    return decorator
