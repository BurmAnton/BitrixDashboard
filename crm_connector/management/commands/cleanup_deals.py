from django.core.management.base import BaseCommand
from django.utils import timezone
from crm_connector.models import Deal
import datetime

class Command(BaseCommand):
    help = 'Очищает устаревшие сделки из базы данных по запросу'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=365, 
                            help='Удалить сделки старше указанного количества дней (по умолчанию 365, установите 0 чтобы отключить)')
        parser.add_argument('--closed-only', action='store_true', 
                            help='Удалять только закрытые сделки')
        parser.add_argument('--dry-run', action='store_true', 
                            help='Не удалять сделки, только показать, сколько будет удалено')
        parser.add_argument('--skip-confirm', action='store_true',
                            help='Пропустить запрос подтверждения')

    def handle(self, *args, **options):
        days = options['days']
        closed_only = options['closed_only']
        dry_run = options['dry_run']
        skip_confirm = options.get('skip_confirm', False)
        
        # Если days = 0, выходим, не удаляя ничего
        if days == 0:
            self.stdout.write(self.style.SUCCESS('Удаление по возрасту отключено (days=0)'))
            return
        
        self.stdout.write(f'Очистка сделок старше {days} дней...')
        
        # Вычисляем дату, старше которой будем удалять сделки
        cutoff_date = timezone.now() - datetime.timedelta(days=days)
        
        # Формируем запрос
        query = Deal.objects.filter(created_at__lt=cutoff_date)
        if closed_only:
            query = query.filter(is_closed=True)
        
        # Получаем количество сделок для удаления
        count = query.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('Нет сделок для удаления.'))
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f'Будет удалено {count} сделок. Используйте команду без --dry-run для фактического удаления.'))
        else:
            # Запрашиваем подтверждение, если не указан флаг skip-confirm
            if not skip_confirm:
                confirm = input(f'Вы действительно хотите удалить {count} сделок? (y/N): ')
                if confirm.lower() != 'y':
                    self.stdout.write(self.style.WARNING('Операция отменена.'))
                    return
            
            deleted, _ = query.delete()
            self.stdout.write(self.style.SUCCESS(f'Успешно удалено {deleted} сделок!')) 