"""
Django management команда для выгрузки базы данных проекта Bitrix Dashboard
Поддерживает различные форматы экспорта: SQL, JSON, CSV
"""

import os
import json
import csv
import subprocess
from datetime import datetime
from io import StringIO
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers import serialize
from django.conf import settings
from django.db import connection
from django.apps import apps


class Command(BaseCommand):
    help = 'Экспорт базы данных в различных форматах (SQL, JSON, CSV)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            type=str,
            choices=['sql', 'json', 'csv', 'all'],
            default='sql',
            help='Формат экспорта: sql, json, csv или all для всех форматов'
        )
        
        parser.add_argument(
            '--output-dir',
            type=str,
            default='.',
            help='Директория для сохранения файлов экспорта (по умолчанию: текущая директория)'
        )
        
        parser.add_argument(
            '--filename-prefix',
            type=str,
            default=f'bitrix_dashboard_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            help='Префикс для имен файлов экспорта'
        )
        
        parser.add_argument(
            '--apps',
            type=str,
            nargs='*',
            default=['crm_connector', 'education_planner'],
            help='Приложения для экспорта (по умолчанию: crm_connector, education_planner)'
        )
        
        parser.add_argument(
            '--include-auth',
            action='store_true',
            help='Включить данные пользователей и групп'
        )
        
        parser.add_argument(
            '--compress',
            action='store_true',
            help='Сжать выходные файлы в gzip'
        )

    def handle(self, *args, **options):
        """Основной метод выполнения команды"""
        
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(exist_ok=True)
        
        filename_prefix = options['filename_prefix']
        export_format = options['format']
        
        self.stdout.write(
            self.style.SUCCESS(f'Начинаем экспорт базы данных в формате: {export_format}')
        )
        
        try:
            if export_format == 'sql' or export_format == 'all':
                self._export_sql(output_dir, filename_prefix, options['compress'])
                
            if export_format == 'json' or export_format == 'all':
                self._export_json(output_dir, filename_prefix, options)
                
            if export_format == 'csv' or export_format == 'all':
                self._export_csv(output_dir, filename_prefix, options)
                
            self.stdout.write(
                self.style.SUCCESS(f'Экспорт завершен успешно! Файлы сохранены в: {output_dir}')
            )
            
        except Exception as e:
            raise CommandError(f'Ошибка при экспорте: {str(e)}')

    def _export_sql(self, output_dir, filename_prefix, compress=False):
        """Экспорт в формате SQL с помощью pg_dump"""
        
        db_settings = settings.DATABASES['default']
        
        # Получаем настройки базы данных
        db_name = db_settings['NAME']
        db_user = db_settings['USER']
        db_password = db_settings['PASSWORD']
        db_host = db_settings['HOST']
        db_port = db_settings['PORT']
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'{filename_prefix}.sql'
        
        if compress:
            filename += '.gz'
            
        output_path = output_dir / filename
        
        # Формируем команду pg_dump
        cmd = [
            'pg_dump',
            '--host', db_host,
            '--port', str(db_port),
            '--username', db_user,
            '--format', 'custom' if compress else 'plain',
            '--verbose',
            '--file', str(output_path),
            db_name
        ]
        
        # Устанавливаем переменную окружения с паролем
        env = os.environ.copy()
        env['PGPASSWORD'] = db_password
        
        self.stdout.write(f'Создаем SQL дамп: {output_path}')
        
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'SQL дамп создан: {output_path}')
            )
            
            # Выводим размер файла
            file_size = output_path.stat().st_size / (1024 * 1024)  # в MB
            self.stdout.write(f'Размер файла: {file_size:.2f} MB')
            
        except subprocess.CalledProcessError as e:
            raise CommandError(f'Ошибка при создании SQL дампа: {e.stderr}')
        except FileNotFoundError:
            raise CommandError(
                'pg_dump не найден. Убедитесь, что PostgreSQL клиент установлен и доступен в PATH'
            )

    def _export_json(self, output_dir, filename_prefix, options):
        """Экспорт в формате JSON"""
        
        filename = f'{filename_prefix}.json'
        output_path = output_dir / filename
        
        # Получаем модели для экспорта
        models_to_export = []
        
        # Добавляем модели из указанных приложений
        for app_name in options['apps']:
            try:
                app = apps.get_app_config(app_name)
                models_to_export.extend(app.get_models())
            except LookupError:
                self.stderr.write(f'Приложение {app_name} не найдено')
                continue
        
        # Добавляем auth модели если нужно
        if options['include_auth']:
            try:
                auth_app = apps.get_app_config('auth')
                models_to_export.extend(auth_app.get_models())
            except LookupError:
                pass
        
        self.stdout.write(f'Экспортируем {len(models_to_export)} моделей в JSON: {output_path}')
        
        export_data = []
        
        for model in models_to_export:
            try:
                # Получаем все объекты модели
                queryset = model.objects.all()
                count = queryset.count()
                
                if count > 0:
                    # Сериализуем данные
                    model_data = serialize('json', queryset)
                    model_objects = json.loads(model_data)
                    
                    export_data.extend(model_objects)
                    
                    self.stdout.write(f'  {model._meta.label}: {count} записей')
                
            except Exception as e:
                self.stderr.write(f'Ошибка при экспорте модели {model._meta.label}: {str(e)}')
                continue
        
        # Сохраняем JSON файл
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            self.stdout.write(
                self.style.SUCCESS(f'JSON экспорт создан: {output_path}')
            )
            
            # Выводим статистику
            file_size = output_path.stat().st_size / (1024 * 1024)  # в MB
            self.stdout.write(f'Размер файла: {file_size:.2f} MB')
            self.stdout.write(f'Всего объектов: {len(export_data)}')
            
        except Exception as e:
            raise CommandError(f'Ошибка при записи JSON файла: {str(e)}')

    def _export_csv(self, output_dir, filename_prefix, options):
        """Экспорт в формате CSV (отдельные файлы для каждой модели)"""
        
        csv_dir = output_dir / f'{filename_prefix}_csv'
        csv_dir.mkdir(exist_ok=True)
        
        # Получаем модели для экспорта
        models_to_export = []
        
        for app_name in options['apps']:
            try:
                app = apps.get_app_config(app_name)
                models_to_export.extend(app.get_models())
            except LookupError:
                self.stderr.write(f'Приложение {app_name} не найдено')
                continue
        
        if options['include_auth']:
            try:
                auth_app = apps.get_app_config('auth')
                models_to_export.extend(auth_app.get_models())
            except LookupError:
                pass
        
        self.stdout.write(f'Экспортируем {len(models_to_export)} моделей в CSV: {csv_dir}')
        
        total_files = 0
        total_records = 0
        
        for model in models_to_export:
            try:
                queryset = model.objects.all()
                count = queryset.count()
                
                if count == 0:
                    continue
                
                # Имя файла для модели
                model_name = f'{model._meta.app_label}_{model._meta.model_name}'
                csv_filename = f'{model_name}.csv'
                csv_path = csv_dir / csv_filename
                
                # Получаем поля модели
                fields = [field.name for field in model._meta.fields]
                
                # Записываем CSV файл
                with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    
                    # Записываем заголовки
                    writer.writerow(fields)
                    
                    # Записываем данные
                    for obj in queryset:
                        row = []
                        for field_name in fields:
                            try:
                                value = getattr(obj, field_name)
                                # Обрабатываем специальные типы данных
                                if value is None:
                                    row.append('')
                                elif isinstance(value, datetime):
                                    row.append(value.isoformat())
                                else:
                                    row.append(str(value))
                            except Exception:
                                row.append('')
                        writer.writerow(row)
                
                self.stdout.write(f'  {model_name}: {count} записей → {csv_filename}')
                total_files += 1
                total_records += count
                
            except Exception as e:
                self.stderr.write(f'Ошибка при экспорте модели {model._meta.label}: {str(e)}')
                continue
        
        self.stdout.write(
            self.style.SUCCESS(f'CSV экспорт создан: {csv_dir}')
        )
        self.stdout.write(f'Создано файлов: {total_files}')
        self.stdout.write(f'Всего записей: {total_records}')

    def _get_database_info(self):
        """Получает информацию о базе данных"""
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del
                FROM pg_stat_user_tables
                ORDER BY schemaname, tablename;
            """)
            
            table_stats = cursor.fetchall()
            
        return {
            'version': version,
            'table_stats': table_stats
        }

