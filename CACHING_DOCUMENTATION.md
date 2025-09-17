# Документация по кешированию данных Атласа

## Обзор

Система кеширования разработана для ускорения загрузки дашборда квот (`quota_summary_dashboard`) путем кеширования данных заявок из Атласа и связанных периодов. Кеш автоматически очищается при импорте новых данных через команду `import_atlas_applications`.

## Архитектура кеширования

### 1. Основные компоненты

- **AtlasDataCache** - основной класс для управления кешем
- **cache_atlas_data** - декоратор для автоматического кеширования функций
- **invalidate_atlas_cache** - декоратор для инвалидации кеша

### 2. Время жизни кеша

- **Стандартное (CACHE_TIMEOUT)**: 2 часа - для основных данных
- **Короткое (CACHE_TIMEOUT_SHORT)**: 30 минут - для часто обновляемых данных
- **Длительное (CACHE_TIMEOUT_LONG)**: 6 часов - для редко изменяемых данных (статусы)

### 3. Кешируемые данные

#### Основные данные Atlas:
- Заявки Atlas (`AtlasApplication`)
- Сделки (`Deal`)
- Воронка продаж (`Pipeline`)
- Статусы Atlas (`AtlasStatus`)

#### Вычисляемые данные:
- Результаты функции `quota_summary_dashboard`
- Результаты функции `get_matching_applications_by_region`
- Результаты функции `get_unmatched_applications`
- Результаты функции `group_quotas_by_region`
- Результаты функции `get_applications_for_alternative_period`

## Команды управления

### 1. Предварительная загрузка кеша

```bash
# Базовая загрузка
python manage.py warm_cache

# Принудительное обновление (очистка + загрузка)
python manage.py warm_cache --force

# Только данные Atlas (без квот)
python manage.py warm_cache --atlas-only
```

### 2. Очистка кеша

```bash
# Полная очистка
python manage.py clear_cache

# Только данные Atlas
python manage.py clear_cache --atlas-only

# Только статусы
python manage.py clear_cache --statuses-only

# Конкретные ключи
python manage.py clear_cache --keys atlas_data:atlas_apps atlas_data:deals
```

### 3. Автоматическая инвалидация

Кеш автоматически очищается при выполнении:
```bash
python manage.py import_atlas_applications [файл.xlsx]
```

## Мониторинг производительности

### Логирование

Система автоматически логирует:
- Cache HIT/MISS для каждой функции
- Время выполнения запросов
- Количество закешированных элементов
- Ошибки при работе с кешем

Пример лога:
```
INFO: Cache HIT for get_matching_applications_by_region - key: atlas_data:a3b2c1... - time: 0.002s
INFO: Cache MISS for get_unmatched_applications - executing function
INFO: Cached result for get_unmatched_applications - key: atlas_data:d4e5f6... - time: 1.234s
```

### Метрики производительности

До внедрения кеширования:
- Загрузка дашборда: ~5-10 секунд
- Повторные запросы: ~5-10 секунд

После внедрения кеширования:
- Первая загрузка: ~5-10 секунд
- Повторные запросы: ~0.5-1 секунда

## Конфигурация

### Redis (рекомендуется)

Для production окружения рекомендуется использовать Redis:

1. Установить переменную окружения:
```bash
export CELERY_BROKER_URL="redis://localhost:6379/0"
```

2. Redis обеспечивает:
- Персистентность кеша между перезагрузками
- Лучшую производительность
- Поддержку паттернов при очистке

### Django Cache (fallback)

Если Redis недоступен, система автоматически использует стандартный Django cache.

## Рекомендации по использованию

### 1. После развертывания

```bash
# Предварительно загрузить кеш
python manage.py warm_cache --force
```

### 2. После импорта данных

Кеш очищается автоматически, но можно принудительно обновить:
```bash
python manage.py import_atlas_applications data.xlsx
python manage.py warm_cache
```

### 3. При проблемах с производительностью

```bash
# Проверить и обновить кеш
python manage.py clear_cache
python manage.py warm_cache --force
```

### 4. Регулярное обслуживание

Добавить в crontab для регулярного обновления:
```cron
# Обновлять кеш каждые 2 часа
0 */2 * * * cd /var/www/BitrixDashboard && python manage.py warm_cache
```

## Troubleshooting

### Проблема: Кеш не работает

1. Проверить подключение к Redis:
```python
python manage.py shell
>>> from education_planner.cache_utils import AtlasDataCache
>>> cache = AtlasDataCache.get_cache()
>>> print(type(cache))
```

2. Проверить логи на наличие ошибок кеширования

### Проблема: Устаревшие данные

1. Очистить кеш:
```bash
python manage.py clear_cache
```

2. Перезагрузить данные:
```bash
python manage.py import_atlas_applications latest_data.xlsx
```

### Проблема: Медленная первая загрузка

Использовать предварительную загрузку:
```bash
python manage.py warm_cache --force
```

## Расширение функционала

### Добавление новой кешируемой функции

```python
from education_planner.cache_utils import cache_atlas_data

@cache_atlas_data(timeout=3600)  # 1 час
def my_heavy_function(param1, param2):
    # Тяжелые вычисления
    return result
```

### Добавление нового типа кеша

В `cache_utils.py`:
```python
class AtlasDataCache:
    # Добавить новый ключ
    MY_DATA_KEY = CACHE_PREFIX + "my_data"
    
    @staticmethod
    def get_cached_my_data():
        # Реализация
        pass
```

## Контакты

При возникновении вопросов или проблем обращайтесь к администратору системы.
