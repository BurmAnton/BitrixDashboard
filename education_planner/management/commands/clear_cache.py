from django.core.management.base import BaseCommand
from education_planner.cache_utils import AtlasDataCache
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Очистка кеша данных Атласа'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keys',
            nargs='+',
            help='Конкретные ключи кеша для очистки'
        )
        parser.add_argument(
            '--atlas-only',
            action='store_true',
            help='Очистить только кеш данных Atlas (заявки и сделки)'
        )
        parser.add_argument(
            '--statuses-only',
            action='store_true',
            help='Очистить только кеш статусов'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Начинаем очистку кеша...'))
        
        if options['keys']:
            # Очистка конкретных ключей
            self.stdout.write(f'Очищаем ключи: {", ".join(options["keys"])}')
            AtlasDataCache.invalidate_specific_keys(options['keys'])
            self.stdout.write(self.style.SUCCESS('Указанные ключи очищены'))
            
        elif options['atlas_only']:
            # Очистка только данных Atlas
            self.stdout.write('Очищаем кеш данных Atlas...')
            keys_to_clear = [
                AtlasDataCache.ATLAS_APPS_KEY,
                AtlasDataCache.DEALS_KEY,
                AtlasDataCache.PIPELINE_KEY
            ]
            AtlasDataCache.invalidate_specific_keys(keys_to_clear)
            self.stdout.write(self.style.SUCCESS('Кеш данных Atlas очищен'))
            
        elif options['statuses_only']:
            # Очистка только статусов
            self.stdout.write('Очищаем кеш статусов...')
            AtlasDataCache.invalidate_specific_keys([AtlasDataCache.ATLAS_STATUSES_KEY])
            self.stdout.write(self.style.SUCCESS('Кеш статусов очищен'))
            
        else:
            # Полная очистка кеша
            self.stdout.write('Выполняем полную очистку кеша...')
            AtlasDataCache.clear_cache()
            self.stdout.write(self.style.SUCCESS('✅ Весь кеш успешно очищен'))
        
        self.stdout.write(
            '\nДля повторной загрузки данных в кеш используйте:\n'
            'python manage.py warm_cache'
        )
