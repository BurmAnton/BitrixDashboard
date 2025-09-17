from django.core.management.base import BaseCommand
from django.utils import timezone
from education_planner.cache_utils import AtlasDataCache
from education_planner.views import (
    get_matching_applications_by_region, 
    get_unmatched_applications
)
from education_planner.models import Quota, EduAgreement, Region
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Предварительная загрузка данных в кеш для ускорения работы'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительно обновить все данные в кеше'
        )
        parser.add_argument(
            '--atlas-only',
            action='store_true',
            help='Загрузить только данные Atlas'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Начинаем предварительную загрузку кеша...'))
        
        if options['force']:
            self.stdout.write('Очищаем существующий кеш...')
            AtlasDataCache.clear_cache()
            self.stdout.write(self.style.SUCCESS('Кеш очищен'))
        
        # Загружаем основные данные Atlas
        self.stdout.write('Загружаем данные Atlas в кеш...')
        pipeline, atlas_apps, deals = AtlasDataCache.get_cached_atlas_data()
        
        if pipeline and atlas_apps and deals:
            self.stdout.write(self.style.SUCCESS(
                f'Загружено: pipeline={pipeline.name}, '
                f'заявок={len(atlas_apps)}, сделок={len(deals)}'
            ))
        else:
            self.stdout.write(self.style.WARNING('Не удалось загрузить данные Atlas'))
        
        # Загружаем статусы
        self.stdout.write('Загружаем статусы Atlas...')
        statuses = AtlasDataCache.get_cached_atlas_statuses()
        if statuses:
            self.stdout.write(self.style.SUCCESS(f'Загружено статусов: {len(statuses)}'))
        else:
            self.stdout.write(self.style.WARNING('Не удалось загрузить статусы'))
        
        if not options['atlas_only']:
            # Предварительно прогреваем несопоставленные заявки
            self.stdout.write('Кешируем несопоставленные заявки...')
            try:
                unmatched = get_unmatched_applications()
                self.stdout.write(self.style.SUCCESS(
                    f'Закешировано несопоставленных заявок: {len(unmatched)}'
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ошибка: {e}'))
            
            # Предварительно прогреваем заявки по регионам для активных квот
            self.stdout.write('Кешируем заявки по регионам для активных квот...')
            try:
                irpo_agreements = EduAgreement.objects.filter(
                    federal_operator='IRPO',
                    status__in=[
                        EduAgreement.AgreementStatus.SIGNED,
                        EduAgreement.AgreementStatus.COMPLETED
                    ]
                )
                
                active_quotas = Quota.objects.filter(
                    agreement__in=irpo_agreements,
                    is_active=True
                ).select_related('education_program').prefetch_related('regions')[:10]  # Ограничиваем для производительности
                
                cached_count = 0
                for quota in active_quotas:
                    for region in quota.regions.all():
                        try:
                            apps = get_matching_applications_by_region(quota, region, quota.start_date)
                            cached_count += 1
                            self.stdout.write(f'  Закешировано: {quota.education_program.name[:30]} - {region.name}')
                        except Exception as e:
                            logger.error(f'Ошибка кеширования для {quota.id} - {region.id}: {e}')
                            
                self.stdout.write(self.style.SUCCESS(
                    f'Закешировано комбинаций квота-регион: {cached_count}'
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Ошибка при кешировании квот: {e}'))
        
        self.stdout.write(self.style.SUCCESS(
            '\n✅ Предварительная загрузка кеша завершена!\n'
            'Кеш будет действителен в течение 2 часов.\n'
            'Для обновления используйте: python manage.py warm_cache --force'
        ))
