#!/usr/bin/env python3
"""
Скрипт для исправления данных аттестации
"""
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BitrixDashboard.settings')
django.setup()

from crm_connector.models import AtlasApplication

def fix_attestation_data():
    """Исправляет данные аттестации для существующих заявок"""
    print("Исправление данных аттестации...")
    
    # Найдем заявки без данных аттестации
    apps_without_attestation = AtlasApplication.objects.filter(
        JSON_ed_progress__isnull=True
    ).exclude(
        education_progress__isnull=True
    ).exclude(
        education_progress__exact=''
    )
    
    print(f"Найдено {apps_without_attestation.count()} заявок без JSON_ed_progress")
    
    fixed_count = 0
    for app in apps_without_attestation[:100]:  # Ограничим до 100 для тестирования
        if app.education_progress:
            try:
                # Создаем базовую структуру данных
                progress_data = {
                    'attestation': app.education_progress,
                    'statistic': {}
                }
                app.JSON_ed_progress = progress_data
                app.save()
                fixed_count += 1
                print(f"Исправлено: {app.email}")
            except Exception as e:
                print(f"Ошибка для {app.email}: {e}")
    
    print(f"Всего исправлено: {fixed_count}")

if __name__ == "__main__":
    fix_attestation_data()
