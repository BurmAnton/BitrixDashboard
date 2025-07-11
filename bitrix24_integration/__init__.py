# Этот файл должен быть импортирован при запуске приложения
# для настройки Celery
from .celery import app as celery_app
 
__all__ = ('celery_app',) 