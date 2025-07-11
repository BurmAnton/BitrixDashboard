import os
from celery import Celery

# Устанавливаем переменную окружения для настроек проекта
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bitrix24_integration.settings')

app = Celery('bitrix24_integration')

# Использовать настройки Django для конфигурации Celery
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автоматическое обнаружение и регистрация задач из всех приложений
app.autodiscover_tasks() 