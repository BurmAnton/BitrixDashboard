"""
Django settings for bitrix24_integration project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from celery.schedules import crontab

# Указываем полный путь к .env файлу
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# Отладочный вывод
print(f"Loading .env from: {env_path}")
print(f"DB_USER from env: {os.getenv('DB_USER', 'not set')}")
print(f"DB_NAME from env: {os.getenv('DB_NAME', 'not set')}")
print(f"DB_PASSWORD from env: {os.getenv('DB_PASSWORD', 'not set')}")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-your-secret-key-here')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True') == 'True'
DJANGO_LOG_LEVEL=DEBUG
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,192.168.1.48').split(',')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crm_connector',
    'education_planner',
    'rest_framework',  # для API если потребуется
    'django_celery_beat',  # для периодических задач
    'simple_history',  # Добавляем django-simple-history для версионирования
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',  # Для отслеживания пользователя в истории
]

ROOT_URLCONF = 'bitrix24_integration.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],  # Убедитесь, что этот путь правильный
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'bitrix24_integration.wsgi.application'

# Database
# https://docs.djangoproject.com/en/4.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'bitrix24_db'),
        'USER': os.getenv('DB_USER', 'bitrix_admin'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'bitrixsep8888'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'Europe/Samara'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Настройки для Битрикс24
BITRIX24_SETTINGS = {
    'DOMAIN': os.getenv('BITRIX24_DOMAIN', 'your-domain.bitrix24.ru').replace('https://', '').replace('http://', ''),
    'CLIENT_SECRET': os.getenv('BITRIX24_CLIENT_SECRET', 'your-client-secret'),
    'REDIRECT_URI': os.getenv('BITRIX24_REDIRECT_URI', 'http://localhost:8000/bitrix24/auth-redirect/'),
}

# Настройки Celery для фоновых задач
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

CELERY_BEAT_SCHEDULE = {
    'sync-pipelines-every-hour': {
        'task': 'crm_connector.tasks.sync_pipelines_task',
        'schedule': crontab(minute=0, hour='*/1'),  # Каждый час
    },
    'sync-deals-every-hour': {
        'task': 'crm_connector.tasks.sync_deals_full',
        'schedule': crontab(minute=30, hour='*/2'),  # Каждые 2 часа
    },
}

# Добавить настройки для правильного перенаправления на страницу входа
LOGIN_URL = '/admin/login/'  # Перенаправляем на стандартную страницу входа Django admin
LOGIN_REDIRECT_URL = '/crm/pipelines/'  # После входа перенаправляем обратно на страницу с воронками 