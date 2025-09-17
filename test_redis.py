#!/usr/bin/env python3
"""
Скрипт для тестирования подключения к Redis и Django кешу
"""
import os
import sys
import django

# Настройка Django
sys.path.append('/var/www/BitrixDashboard')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bitrix24_integration.settings')
django.setup()

from django.core.cache import cache
from education_planner.cache_utils import AtlasDataCache
import redis


def test_redis_connection():
    """Тестирование прямого подключения к Redis"""
    print("=== Тестирование прямого подключения к Redis ===")
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        result = r.ping()
        print(f"✅ Redis PING: {result}")
        
        # Тест записи/чтения
        r.set('test_key', 'test_value', ex=60)
        value = r.get('test_key')
        print(f"✅ Redis set/get test: {value.decode() if value else None}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к Redis: {e}")
        return False


def test_django_cache():
    """Тестирование Django кеша"""
    print("\n=== Тестирование Django кеша ===")
    try:
        # Тест записи в кеш
        cache.set('test_django_key', 'test_django_value', 60)
        value = cache.get('test_django_key')
        print(f"✅ Django cache set/get test: {value}")
        
        # Информация о кеше
        print(f"✅ Cache backend: {cache.__class__.__name__}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка Django кеша: {e}")
        return False


def test_atlas_cache():
    """Тестирование AtlasDataCache"""
    print("\n=== Тестирование AtlasDataCache ===")
    try:
        # Тест получения кеша
        cache_instance = AtlasDataCache.get_cache()
        print(f"✅ AtlasDataCache instance: {type(cache_instance)}")
        
        # Тест создания ключа
        test_key = AtlasDataCache.make_key('test_function', ['arg1'], {'kwarg1': 'value1'})
        print(f"✅ Generated cache key: {test_key[:50]}...")
        
        # Тест записи/чтения через AtlasDataCache
        cache_instance.set(test_key, {'test': 'data'}, 60)
        result = cache_instance.get(test_key)
        print(f"✅ AtlasDataCache set/get test: {result}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка AtlasDataCache: {e}")
        return False


def test_cache_commands():
    """Тестирование команд управления кешем"""
    print("\n=== Тестирование команд управления кешем ===")
    try:
        # Предварительная загрузка кеша
        print("Тестируем предварительную загрузку кеша...")
        AtlasDataCache.warm_up_cache()
        print("✅ Предварительная загрузка кеша выполнена")
        
        # Получение данных Atlas
        print("Тестируем получение данных Atlas...")
        pipeline, atlas_apps, deals = AtlasDataCache.get_cached_atlas_data()
        
        if pipeline:
            print(f"✅ Pipeline найден: {pipeline.name}")
        if atlas_apps:
            print(f"✅ Atlas apps загружены: {len(atlas_apps)} записей")
        if deals:
            print(f"✅ Deals загружены: {len(deals)} записей")
            
        return True
    except Exception as e:
        print(f"❌ Ошибка при тестировании команд: {e}")
        return False


def main():
    """Основная функция тестирования"""
    print("🚀 Начинаем тестирование Redis и кеширования...")
    
    tests = [
        test_redis_connection,
        test_django_cache,
        test_atlas_cache,
        test_cache_commands
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте {test.__name__}: {e}")
            results.append(False)
    
    # Итоги
    print(f"\n{'='*50}")
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print(f"✅ Успешных тестов: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 Все тесты пройдены успешно! Redis настроен корректно.")
        print("\n📝 Рекомендации:")
        print("1. Запустите: python manage.py warm_cache --force")
        print("2. Проверьте производительность дашборда")
        print("3. Настройте регулярное обновление кеша через cron")
    else:
        print("⚠️  Некоторые тесты не пройдены. Проверьте конфигурацию.")
    
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
