#!/usr/bin/env python
"""
Пример использования системы правил определения стадий

Этот скрипт демонстрирует, как работает новая система правил
для определения этапа воронки на основе статусов заявки.
"""

import os
import sys
import django

# Настройка Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bitrix24_integration.settings')
django.setup()

from crm_connector.models import Pipeline, Stage, AtlasStatus, RRStatus, StageRule


def create_example_rules():
    """Создает примеры правил для демонстрации"""
    
    # Получаем воронку
    pipeline = Pipeline.objects.filter(name="Заявки (граждане)").first()
    if not pipeline:
        print("Воронка 'Заявки (граждане)' не найдена. Запустите сначала синхронизацию воронок.")
        return
    
    # Создаем статусы для примера
    atlas_new, _ = AtlasStatus.objects.get_or_create(
        name="Новая", defaults={'order': 10}
    )
    atlas_approved, _ = AtlasStatus.objects.get_or_create(
        name="Одобрена", defaults={'order': 20}
    )
    atlas_rejected, _ = AtlasStatus.objects.get_or_create(
        name="Отклонена", defaults={'order': 30}
    )
    
    rr_new, _ = RRStatus.objects.get_or_create(
        name="Новая", defaults={'order': 10}
    )
    rr_docs_check, _ = RRStatus.objects.get_or_create(
        name="Ожидает проверки документов", defaults={'order': 20}
    )
    rr_contract, _ = RRStatus.objects.get_or_create(
        name="Договор на подписании", defaults={'order': 30}
    )
    
    # Получаем стадии
    stages = Stage.objects.filter(pipeline=pipeline)
    stage_new = stages.filter(bitrix_id__endswith=":NEW").first()
    stage_preparation = stages.filter(bitrix_id__endswith=":PREPARATION").first()
    stage_executing = stages.filter(bitrix_id__endswith=":EXECUTING").first()
    stage_lose = stages.filter(bitrix_id__endswith=":LOSE").first()
    
    if not all([stage_new, stage_preparation, stage_executing, stage_lose]):
        print("Не все стадии найдены. Запустите синхронизацию стадий.")
        return
    
    # Создаем правила
    rules = [
        # Правило 1: Если в Атлас отклонена - сразу в отклоненные (высокий приоритет)
        {
            'pipeline': pipeline,
            'atlas_status': atlas_rejected,
            'rr_status': None,
            'target_stage': stage_lose,
            'priority': 5,
            'description': 'Отклоненные в Атлас заявки сразу переходят в финальную стадию отклонения'
        },
        # Правило 2: Новая в обеих системах - начальная стадия
        {
            'pipeline': pipeline,
            'atlas_status': atlas_new,
            'rr_status': rr_new,
            'target_stage': stage_new,
            'priority': 20,
            'description': 'Новые заявки начинают с первой стадии'
        },
        # Правило 3: Одобрена в Атлас + документы на проверке в РР
        {
            'pipeline': pipeline,
            'atlas_status': atlas_approved,
            'rr_status': rr_docs_check,
            'target_stage': stage_preparation,
            'priority': 30,
            'description': 'Одобренные заявки с документами на проверке'
        },
        # Правило 4: Только статус РР - договор на подписании
        {
            'pipeline': pipeline,
            'atlas_status': None,
            'rr_status': rr_contract,
            'target_stage': stage_executing,
            'priority': 50,
            'description': 'Заявки с договором на подписании'
        }
    ]
    
    print("\nСоздаем примеры правил:")
    for rule_data in rules:
        rule, created = StageRule.objects.get_or_create(
            pipeline=rule_data['pipeline'],
            atlas_status=rule_data['atlas_status'],
            rr_status=rule_data['rr_status'],
            defaults={
                'target_stage': rule_data['target_stage'],
                'priority': rule_data['priority'],
                'description': rule_data['description']
            }
        )
        if created:
            print(f"✓ Создано правило: {rule}")
        else:
            print(f"  Правило уже существует: {rule}")


def test_stage_determination():
    """Тестирует определение стадий для разных комбинаций статусов"""
    
    pipeline = Pipeline.objects.filter(name="Заявки (граждане)").first()
    if not pipeline:
        print("Воронка не найдена!")
        return
    
    print("\n\nТестирование определения стадий:")
    print("-" * 60)
    
    test_cases = [
        ("Новая", "Новая", "Новая заявка в обеих системах"),
        ("Отклонена", "Новая", "Отклонена в Атлас, новая в РР"),
        ("Одобрена", "Ожидает проверки документов", "Одобрена + документы на проверке"),
        ("Одобрена", "Договор на подписании", "Одобрена + договор"),
        (None, "Договор на подписании", "Только статус РР"),
        ("В обработке", "Неизвестный статус", "Неизвестная комбинация"),
    ]
    
    for atlas_status, rr_status, description in test_cases:
        stage = StageRule.determine_stage_for_deal(
            pipeline=pipeline,
            atlas_status_name=atlas_status,
            rr_status_name=rr_status
        )
        
        print(f"\n{description}:")
        print(f"  Атлас: {atlas_status or 'не указан'}")
        print(f"  РР: {rr_status or 'не указан'}")
        print(f"  → Стадия: {stage.name if stage else 'Не определена (будет использована логика из JSON)'}")


if __name__ == "__main__":
    print("Демонстрация системы правил определения стадий")
    print("=" * 60)
    
    create_example_rules()
    test_stage_determination()
    
    print("\n\nДля управления правилами используйте админку Django или команду:")
    print("python manage.py init_stage_rules") 