from django.core.management.base import BaseCommand
from crm_connector.models import AtlasApplication

class Command(BaseCommand):
    help = 'Исправляет данные аттестации'

    def handle(self, *args, **options):
        self.stdout.write("Исправление данных аттестации...")
        
        # Найдем заявки без данных аттестации
        apps_without_attestation = AtlasApplication.objects.filter(
            JSON_ed_progress__isnull=True
        ).exclude(
            education_progress__isnull=True
        ).exclude(
            education_progress__exact=''
        )
        
        self.stdout.write(f"Найдено {apps_without_attestation.count()} заявок без JSON_ed_progress")
        
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
                    self.stdout.write(f"Исправлено: {app.email}")
                except Exception as e:
                    self.stdout.write(f"Ошибка для {app.email}: {e}")
        
        self.stdout.write(f"Всего исправлено: {fixed_count}")
