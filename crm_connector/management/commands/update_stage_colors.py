from django.core.management.base import BaseCommand
from crm_connector.models import Stage

class Command(BaseCommand):
    help = 'Обновляет цвета стадий в соответствии с их типами'

    def handle(self, *args, **options):
        stages = Stage.objects.all()
        updated = 0
        
        for stage in stages:
            old_color = stage.color
            stage.set_color_by_type()
            if old_color != stage.color:
                stage.save()
                updated += 1
                self.stdout.write(f'Обновлен цвет для этапа "{stage.name}": {old_color} → {stage.color}')
        
        self.stdout.write(self.style.SUCCESS(f'Успешно обновлены цвета для {updated} из {stages.count()} этапов'))