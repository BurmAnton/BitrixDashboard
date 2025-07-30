# Инструкция по развертыванию Bitrix Dashboard на продакшн

## Файлы для развертывания

1. **Код приложения**: Весь проект из директории `/home/anton/Projects/bitrix_dashbord/`
2. **Дамп базы данных**: 
   - `bitrix24_db_dump_YYYYMMDD_HHMMSS.dump` (42MB) - бинарный дамп PostgreSQL
   - `bitrix24_db_dump_YYYYMMDD_HHMMSS.sql.gz` (сжатый SQL дамп)

## Требования к серверу

- Python 3.12+
- PostgreSQL 12+
- Redis (для Celery)
- Nginx
- Git

## Шаги развертывания

### 1. Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка зависимостей
sudo apt install python3 python3-pip python3-venv postgresql postgresql-contrib redis-server nginx git -y

# Создание пользователя базы данных
sudo -u postgres createuser --interactive bitrix_admin
sudo -u postgres createdb bitrix24_db_prod -O bitrix_admin

# Установка пароля для пользователя БД
sudo -u postgres psql -c "ALTER USER bitrix_admin PASSWORD 'НОВЫЙ_ПАРОЛЬ';"
```

### 2. Загрузка кода

```bash
# Клонирование репозитория или загрузка архива
cd /var/www/
sudo git clone https://github.com/ваш-репозиторий/bitrix_dashboard.git
sudo chown -R www-data:www-data bitrix_dashboard
cd bitrix_dashboard

# Создание виртуального окружения
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

### 3. Восстановление базы данных

**Вариант A: Из бинарного дампа (рекомендуется)**
```bash
# Копируем дамп на сервер
scp bitrix24_db_dump_*.dump user@server:/tmp/

# Восстанавливаем
PGPASSWORD=НОВЫЙ_ПАРОЛЬ pg_restore -h localhost -U bitrix_admin -d bitrix24_db_prod --clean --if-exists --verbose /tmp/bitrix24_db_dump_*.dump
```

**Вариант B: Из SQL дампа**
```bash
# Копируем и распаковываем
scp bitrix24_db_dump_*.sql.gz user@server:/tmp/
gunzip /tmp/bitrix24_db_dump_*.sql.gz

# Восстанавливаем
PGPASSWORD=НОВЫЙ_ПАРОЛЬ psql -h localhost -U bitrix_admin -d bitrix24_db_prod < /tmp/bitrix24_db_dump_*.sql
```

### 4. Настройка окружения

```bash
# Создание .env файла
cp .env.example .env

# Редактирование настроек
nano .env
```

**Пример .env для продакшн:**
```env
DEBUG=False
SECRET_KEY=ваш-очень-секретный-ключ
ALLOWED_HOSTS=ваш-домен.ru,IP_сервера

DB_NAME=bitrix24_db_prod
DB_USER=bitrix_admin
DB_PASSWORD=НОВЫЙ_ПАРОЛЬ
DB_HOST=localhost
DB_PORT=5432

BITRIX24_DOMAIN=ваш-домен.bitrix24.ru
BITRIX24_CLIENT_SECRET=ваш-webhook-код

CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 5. Применение миграций и сборка статики

```bash
# Активируем окружение
source env/bin/activate

# Применяем миграции
python manage.py migrate

# Собираем статические файлы
python manage.py collectstatic --noinput

# Создаем суперпользователя
python manage.py createsuperuser
```

### 6. Настройка Nginx

```bash
# Создаем конфигурацию
sudo nano /etc/nginx/sites-available/bitrix_dashboard
```

**Конфигурация nginx:**
```nginx
server {
    listen 80;
    server_name ваш-домен.ru;

    # Статические файлы
    location /static/ {
        alias /var/www/bitrix_dashboard/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Основное приложение
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Увеличиваем таймауты
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }
}
```

```bash
# Активируем сайт
sudo ln -s /etc/nginx/sites-available/bitrix_dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7. Настройка systemd сервисов

**Django приложение:**
```bash
sudo nano /etc/systemd/system/bitrix_dashboard.service
```

```ini
[Unit]
Description=Bitrix Dashboard Django App
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/bitrix_dashboard
Environment=PATH=/var/www/bitrix_dashboard/env/bin
ExecStart=/var/www/bitrix_dashboard/env/bin/python manage.py runserver 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

**Celery Worker:**
```bash
sudo nano /etc/systemd/system/bitrix_celery.service
```

```ini
[Unit]
Description=Bitrix Dashboard Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/bitrix_dashboard
Environment=PATH=/var/www/bitrix_dashboard/env/bin
ExecStart=/var/www/bitrix_dashboard/env/bin/celery -A bitrix24_integration worker -l info
Restart=always

[Install]
WantedBy=multi-user.target
```

**Celery Beat:**
```bash
sudo nano /etc/systemd/system/bitrix_celery_beat.service
```

```ini
[Unit]
Description=Bitrix Dashboard Celery Beat
After=network.target redis.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/bitrix_dashboard
Environment=PATH=/var/www/bitrix_dashboard/env/bin
ExecStart=/var/www/bitrix_dashboard/env/bin/celery -A bitrix24_integration beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
Restart=always

[Install]
WantedBy=multi-user.target
```

### 8. Запуск сервисов

```bash
# Перезагружаем демонов
sudo systemctl daemon-reload

# Запускаем и добавляем в автозагрузку
sudo systemctl enable bitrix_dashboard bitrix_celery bitrix_celery_beat
sudo systemctl start bitrix_dashboard bitrix_celery bitrix_celery_beat

# Проверяем статус
sudo systemctl status bitrix_dashboard
sudo systemctl status bitrix_celery
sudo systemctl status bitrix_celery_beat
```

### 9. Настройка SSL (опционально)

```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx -y

# Получение сертификата
sudo certbot --nginx -d ваш-домен.ru
```

## Важные данные в базе

База содержит:
- ✅ **1981 сделка** из Битрикс24
- ✅ **316 заявок** из системы Атлас
- ✅ **29 правил StageRule** для определения стадий
- ✅ **Статусы Атлас и РР** для маппинга
- ✅ **Конфигурация воронок и стадий**
- ✅ **Пользователи и права доступа**

## Проверка работоспособности

1. Откройте `http://ваш-домен.ru/admin/` - должна загрузиться админка Django
2. Войдите в систему
3. Перейдите в `http://ваш-домен.ru/crm/pipelines/` - должна отображаться статистика
4. Попробуйте функцию "Проверка стадии по статусам"
5. Проверьте импорт из Атласа

## Обслуживание

```bash
# Просмотр логов
sudo journalctl -u bitrix_dashboard -f
sudo journalctl -u bitrix_celery -f

# Перезапуск сервисов
sudo systemctl restart bitrix_dashboard
sudo systemctl restart bitrix_celery

# Обновление кода
cd /var/www/bitrix_dashboard
git pull
source env/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart bitrix_dashboard
``` 