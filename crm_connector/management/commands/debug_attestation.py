from django.core.management.base import BaseCommand
from crm_connector.models import AtlasApplication

class Command(BaseCommand):
    help = 'Отлаживает данные аттестации'

    def handle(self, *args, **options):
        self.stdout.write("=== ОТЛАДКА ДАННЫХ ATLAS APPLICATION ===")
        
        total_apps = AtlasApplication.objects.count()
        self.stdout.write(f"Всего заявок: {total_apps}")
        
        apps_with_progress = AtlasApplication.objects.exclude(JSON_ed_progress__isnull=True).count()
        self.stdout.write(f"Заявок с JSON_ed_progress: {apps_with_progress}")
        
        apps_with_attestation = AtlasApplication.objects.filter(
            JSON_ed_progress__attestation__isnull=False
        ).count()
        self.stdout.write(f"Заявок с данными attestation: {apps_with_attestation}")
        
        # Проверим несколько записей
        self.stdout.write("\n=== ПРИМЕРЫ ЗАПИСЕЙ ===")
        sample_apps = AtlasApplication.objects.all()[:5]
        
        for app in sample_apps:
            self.stdout.write(f"\nЗаявка: {app.application_id}")
            self.stdout.write(f"Email: {app.email}")
            self.stdout.write(f"Программа: {app.program}")
            self.stdout.write(f"JSON_ed_progress: {app.JSON_ed_progress}")
            if app.JSON_ed_progress:
                self.stdout.write(f"Attestation: {app.JSON_ed_progress.get('attestation', 'НЕТ')}")
            self.stdout.write("-" * 50)
