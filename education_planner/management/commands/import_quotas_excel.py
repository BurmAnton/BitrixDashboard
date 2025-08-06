from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from education_planner.models import EduAgreement, Quota, EducationProgram, Region
import pandas as pd
from datetime import datetime
import os


class Command(BaseCommand):
    help = 'Импорт квот из Excel файла'

    def add_arguments(self, parser):
        parser.add_argument(
            'file_path', 
            type=str, 
            help='Путь к Excel файлу с квотами'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать результат без сохранения в базу данных',
        )

    def handle(self, *args, **options):
        file_path = options['file_path']
        dry_run = options['dry_run']

        if not os.path.exists(file_path):
            raise CommandError(f'Файл {file_path} не найден')

        try:
            # Читаем Excel файл
            df = pd.read_excel(file_path)
            
            # Проверяем необходимые колонки
            required_columns = [
                'договор_номер', 'программа_название', 'программа_часы', 
                'программа_форма', 'регионы', 'количество', 'стоимость_за_заявку'
            ]
            optional_columns = ['дата_начала', 'дата_окончания']
            
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise CommandError(f'Отсутствуют обязательные колонки: {", ".join(missing_columns)}')

            self.stdout.write(f'Найдено {len(df)} строк для импорта')
            
            # Статистика
            created_count = 0
            error_count = 0
            errors = []

            with transaction.atomic():
                for index, row in df.iterrows():
                    try:
                        # Ищем договор
                        agreement = EduAgreement.objects.filter(
                            number=str(row['договор_номер']).strip()
                        ).first()
                        
                        if not agreement:
                            error_msg = f'Строка {index + 2}: Договор {row["договор_номер"]} не найден'
                            errors.append(error_msg)
                            error_count += 1
                            continue

                        # Ищем программу обучения
                        program = EducationProgram.objects.filter(
                            name__icontains=str(row['программа_название']).strip(),
                            academic_hours=int(row['программа_часы'])
                        ).first()
                        
                        if not program:
                            error_msg = f'Строка {index + 2}: Программа "{row["программа_название"]}" ({row["программа_часы"]} ч.) не найдена'
                            errors.append(error_msg)
                            error_count += 1
                            continue

                        # Парсим регионы
                        regions_names = [name.strip() for name in str(row['регионы']).split(',')]
                        regions = []
                        for region_name in regions_names:
                            region = Region.objects.filter(name__icontains=region_name).first()
                            if region:
                                regions.append(region)
                            else:
                                error_msg = f'Строка {index + 2}: Регион "{region_name}" не найден'
                                errors.append(error_msg)
                        
                        if not regions:
                            error_count += 1
                            continue

                        # Обрабатываем даты
                        start_date = None
                        end_date = None
                        
                        if 'дата_начала' in df.columns and pd.notna(row['дата_начала']):
                            try:
                                if isinstance(row['дата_начала'], str):
                                    start_date = datetime.strptime(row['дата_начала'], '%d.%m.%Y').date()
                                else:
                                    start_date = row['дата_начала'].date()
                            except (ValueError, AttributeError):
                                error_msg = f'Строка {index + 2}: Неверный формат даты начала'
                                errors.append(error_msg)
                        
                        if 'дата_окончания' in df.columns and pd.notna(row['дата_окончания']):
                            try:
                                if isinstance(row['дата_окончания'], str):
                                    end_date = datetime.strptime(row['дата_окончания'], '%d.%m.%Y').date()
                                else:
                                    end_date = row['дата_окончания'].date()
                            except (ValueError, AttributeError):
                                error_msg = f'Строка {index + 2}: Неверный формат даты окончания'
                                errors.append(error_msg)

                        # Валидация дат
                        if start_date and end_date and start_date > end_date:
                            error_msg = f'Строка {index + 2}: Дата начала не может быть позже даты окончания'
                            errors.append(error_msg)
                            error_count += 1
                            continue

                        # Создаем квоту
                        if not dry_run:
                            quota = Quota.objects.create(
                                agreement=agreement,
                                education_program=program,
                                quantity=int(row['количество']),
                                cost_per_quota=float(row['стоимость_за_заявку']),
                                start_date=start_date,
                                end_date=end_date
                            )
                            quota.regions.set(regions)
                            
                        created_count += 1
                        
                        if dry_run:
                            self.stdout.write(
                                f'[ТЕСТ] Строка {index + 2}: Квота для договора {agreement.number}, '
                                f'программа {program.name}, регионы: {", ".join([r.name for r in regions])}'
                            )
                        else:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'Строка {index + 2}: Квота успешно создана для договора {agreement.number}'
                                )
                            )

                    except Exception as e:
                        error_msg = f'Строка {index + 2}: Ошибка импорта - {str(e)}'
                        errors.append(error_msg)
                        error_count += 1

                if dry_run:
                    # Откатываем транзакцию при тестовом запуске
                    transaction.set_rollback(True)

            # Выводим статистику
            self.stdout.write(f'\n=== РЕЗУЛЬТАТЫ ИМПОРТА ===')
            self.stdout.write(f'Успешно обработано: {created_count}')
            self.stdout.write(f'Ошибок: {error_count}')
            
            if errors:
                self.stdout.write(f'\n=== ОШИБКИ ===')
                for error in errors:
                    self.stdout.write(self.style.ERROR(error))

            if dry_run:
                self.stdout.write(
                    self.style.WARNING('\nЭто был тестовый запуск. Для реального импорта уберите --dry-run')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'\nИмпорт завершен! Создано квот: {created_count}')
                )

        except Exception as e:
            raise CommandError(f'Ошибка при обработке файла: {str(e)}')