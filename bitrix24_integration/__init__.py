# Этот файл должен быть импортирован при запуске приложения
# для настройки Celery
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Celery не установлен - работаем без него
    pass 