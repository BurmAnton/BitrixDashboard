import os
import json
from django.core.management.base import BaseCommand
from django.db import transaction
from crm_connector.models import Pipeline, Stage, AtlasStatus, RRStatus, StageRule


class Command(BaseCommand):
    help = 'Инициализирует статусы и правила определения стадий из JSON файла'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--pipeline-name',
            type=str,
            default='Заявки (граждане)',
            help='Название воронки для создания правил'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Инициализация статусов и правил определения стадий...'))
        
        # Загружаем данные из JSON файла
        mapping_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'atlas_field_mapping.json'
        )
        
        with open(mapping_file, 'r', encoding='utf-8') as f:
            field_mapping = json.load(f)
        
        # Получаем воронку
        pipeline_name = options['pipeline_name']
        try:
            pipeline = Pipeline.objects.get(name=pipeline_name)
        except Pipeline.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Воронка '{pipeline_name}' не найдена!"))
            return
        
        with transaction.atomic():
            # Создаем статусы из stage_mapping
            stage_map = field_mapping.get('stage_mapping', {})
            
            # Сначала собираем все уникальные статусы
            atlas_statuses = set()
            rr_statuses = set()
            
            # Из текущего маппинга предполагаем, что это статусы РР (т.к. они основные)
            for status_name in stage_map.keys():
                rr_statuses.add(status_name)
            
            # Создаем статусы РР
            self.stdout.write("Создаем статусы РР...")
            order = 10
            for status_name in sorted(rr_statuses):
                status, created = RRStatus.objects.get_or_create(
                    name=status_name,
                    defaults={'order': order}
                )
                if created:
                    self.stdout.write(f"  Создан статус РР: {status_name}")
                order += 10
            
            # Создаем базовые статусы Атлас (можно расширить позже)
            self.stdout.write("Создаем статусы Атлас...")
            basic_atlas_statuses = [
                "Новая",
                "В обработке", 
                "Одобрена",
                "Отклонена",
                "Завершена"
            ]
            order = 10
            for status_name in basic_atlas_statuses:
                status, created = AtlasStatus.objects.get_or_create(
                    name=status_name,
                    defaults={'order': order}
                )
                if created:
                    self.stdout.write(f"  Создан статус Атлас: {status_name}")
                order += 10
            
            # Создаем правила на основе существующего маппинга
            self.stdout.write("Создаем правила определения стадий...")
            priority = 10
            
            for status_name, stage_code in stage_map.items():
                # Получаем статус РР
                try:
                    rr_status = RRStatus.objects.get(name=status_name)
                except RRStatus.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"  Статус РР '{status_name}' не найден, пропускаем"))
                    continue
                
                # Получаем стадию
                stage_bitrix_id = f"C{pipeline.bitrix_id}:{stage_code}"
                try:
                    stage = Stage.objects.get(bitrix_id=stage_bitrix_id)
                except Stage.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"  Стадия {stage_bitrix_id} не найдена, пропускаем"))
                    continue
                
                # Создаем правило
                rule, created = StageRule.objects.get_or_create(
                    pipeline=pipeline,
                    rr_status=rr_status,
                    atlas_status=None,  # Только по статусу РР
                    defaults={
                        'target_stage': stage,
                        'priority': priority,
                        'description': f'Автоматически создано из JSON: {status_name} → {stage.name}'
                    }
                )
                
                if created:
                    self.stdout.write(f"  Создано правило: {rule}")
                priority += 10
            
            # Создаем комбинированные правила для некоторых случаев
            self.stdout.write("Создаем комбинированные правила...")
            
            # Пример: если статус в Атлас "Отклонена", независимо от РР -> стадия "Отклонена"
            try:
                atlas_rejected = AtlasStatus.objects.get(name="Отклонена")
                stage_lose = Stage.objects.get(bitrix_id=f"C{pipeline.bitrix_id}:LOSE")
                
                rule, created = StageRule.objects.get_or_create(
                    pipeline=pipeline,
                    atlas_status=atlas_rejected,
                    rr_status=None,
                    defaults={
                        'target_stage': stage_lose,
                        'priority': 5,  # Высокий приоритет
                        'description': 'Если заявка отклонена в Атлас - сразу в отклоненные'
                    }
                )
                if created:
                    self.stdout.write(f"  Создано правило: {rule}")
            except (AtlasStatus.DoesNotExist, Stage.DoesNotExist) as e:
                self.stdout.write(self.style.WARNING(f"  Не удалось создать правило для отклоненных: {e}"))
        
        self.stdout.write(self.style.SUCCESS('Инициализация завершена!')) 