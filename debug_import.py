#!/usr/bin/env python3
"""
Скрипт для отладки импорта данных аттестации
"""
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BitrixDashboard.settings')
django.setup()

from crm_connector.models import AtlasApplication
import pandas as pd

def debug_atlas_applications():
    """Отлаживает данные AtlasApplication"""
    print("=== ОТЛАДКА ДАННЫХ ATLAS APPLICATION ===")
    
    total_apps = AtlasApplication.objects.count()
    print(f"Всего заявок: {total_apps}")
    
    apps_with_progress = AtlasApplication.objects.exclude(JSON_ed_progress__isnull=True).count()
    print(f"Заявок с JSON_ed_progress: {apps_with_progress}")
    
    apps_with_attestation = AtlasApplication.objects.filter(
        JSON_ed_progress__attestation__isnull=False
    ).count()
    print(f"Заявок с данными attestation: {apps_with_attestation}")
    
    # Проверим несколько записей
    print("\n=== ПРИМЕРЫ ЗАПИСЕЙ ===")
    sample_apps = AtlasApplication.objects.all()[:5]
    
    for app in sample_apps:
        print(f"\nЗаявка: {app.application_id}")
        print(f"Email: {app.email}")
        print(f"Программа: {app.program}")
        print(f"JSON_ed_progress: {app.JSON_ed_progress}")
        if app.JSON_ed_progress:
            print(f"Attestation: {app.JSON_ed_progress.get('attestation', 'НЕТ')}")
        print("-" * 50)

def debug_excel_structure(file_path):
    """Отлаживает структуру Excel файла"""
    print(f"\n=== ОТЛАДКА EXCEL ФАЙЛА: {file_path} ===")
    
    try:
        df = pd.read_excel(file_path, header=None, engine='openpyxl')
        header_row = df.iloc[0]
        
        print(f"Количество колонок: {len(header_row)}")
        print(f"Первые 30 заголовков:")
        for i, header in enumerate(header_row[:30]):
            print(f"  {i}: {header}")
            
        # Поиск колонок с аттестацией
        print(f"\nПоиск колонок с аттестацией:")
        for i, header in enumerate(header_row):
            if pd.notna(header) and any(keyword in str(header).lower() 
                                       for keyword in ["аттестация", "тест", "тестирование", "экзамен"]):
                print(f"  Найдено в колонке {i}: {header}")
                
    except Exception as e:
        print(f"Ошибка чтения файла: {e}")

if __name__ == "__main__":
    debug_atlas_applications()
    
    # Если передан путь к файлу, отладим его
    if len(sys.argv) > 1:
        debug_excel_structure(sys.argv[1])
