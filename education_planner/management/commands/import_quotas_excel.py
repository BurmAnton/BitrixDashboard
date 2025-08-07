from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from education_planner.models import EduAgreement, Quota, EducationProgram, Region
import pandas as pd
from datetime import datetime
import os
import re


class Command(BaseCommand):
    help = 'Импорт квот из Excel файла'
    
    def clean_text_data(self, text):
        """Очистка текстовых данных от лишних символов"""
        if not text or pd.isna(text):
            return ""
        
        text = str(text).strip()
        # Убираем переводы строк и табуляции
        text = re.sub(r'[\n\r\t]+', ' ', text)
        # Убираем множественные пробелы
        text = re.sub(r'\s+', ' ', text)
        # Убираем пробелы в начале и конце
        text = text.strip()
        
        return text
    
    def find_or_create_region(self, region_name_input):
        """Поиск региона по названию или создание псевдонима"""
        region_name = self.clean_text_data(region_name_input)
        
        if not region_name:
            return None, f'Пустое название региона'
        
        # Сначала точный поиск
        region = Region.objects.filter(name__iexact=region_name).first()
        if region:
            return region, None
        
        # Поиск по частичному совпадению
        region = Region.objects.filter(name__icontains=region_name).first()
        if region:
            return region, None
        
        # Если не найден, создаем новый регион
        try:
            region = Region.objects.create(
                name=region_name,
                code=region_name[:10].upper().replace(' ', '_').replace('-', '_'),
                is_active=True
            )
            return region, f'Создан новый регион "{region_name}"'
        except Exception as e:
            return None, f'Ошибка создания региона "{region_name}": {str(e)}'

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
                'договор_номер', 'программа_название', 'программа_тип', 'программа_часы', 
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
                        # Очищаем текстовые данные
                        agreement_number = self.clean_text_data(row['договор_номер'])
                        program_name = self.clean_text_data(row['программа_название'])
                        program_type = self.clean_text_data(row['программа_тип'])
                        program_form = self.clean_text_data(row['программа_форма'])
                        regions_text = self.clean_text_data(row['регионы'])
                        
                        # Ищем договор
                        agreement = EduAgreement.objects.filter(
                            number=agreement_number
                        ).first()
                        
                        if not agreement:
                            error_msg = f'Строка {index + 2}: Договор {agreement_number} не найден'
                            errors.append(error_msg)
                            error_count += 1
                            continue

                        # Ищем или создаем программу обучения
                        program = EducationProgram.objects.filter(
                            name__icontains=program_name,
                            academic_hours=int(row['программа_часы'])
                        ).first()
                        
                        if not program:
                            # Создаем программу автоматически
                            try:
                                # Определяем тип программы
                                program_type_choices = {
                                    'повышение квалификации': EducationProgram.ProgramType.QUALIFICATION_UPGRADE,
                                    'профессиональная переподготовка': EducationProgram.ProgramType.PROFESSIONAL_RETRAINING,
                                    'программы профессионального обучения': EducationProgram.ProgramType.PROFESSIONAL_TRAINING
                                }
                                
                                program_type_key = program_type.lower()
                                program_type_value = program_type_choices.get(program_type_key, EducationProgram.ProgramType.QUALIFICATION_UPGRADE)
                                
                                # Определяем форму обучения
                                study_form_choices = {
                                    'очная': EducationProgram.StudyForm.FULL_TIME,
                                    'заочная': EducationProgram.StudyForm.PART_TIME,
                                    'очно-заочная': EducationProgram.StudyForm.MIXED
                                }
                                
                                study_form_key = program_form.lower()
                                study_form_value = study_form_choices.get(study_form_key, EducationProgram.StudyForm.FULL_TIME)
                                
                                program = EducationProgram.objects.create(
                                    name=program_name,
                                    program_type=program_type_value,
                                    academic_hours=int(row['программа_часы']),
                                    study_form=study_form_value,
                                    description=f'Автоматически создана при импорте квот'
                                )
                                
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f'Строка {index + 2}: Создана программа "{program_name}"'
                                    )
                                )
                                
                            except Exception as e:
                                error_msg = f'Строка {index + 2}: Ошибка создания программы "{program_name}" - {str(e)}'
                                errors.append(error_msg)
                                error_count += 1
                                continue

                        # Парсим регионы с автоматическим созданием
                        regions_names = [self.clean_text_data(name) for name in regions_text.split(',') if self.clean_text_data(name)]
                        regions = []
                        region_messages = []
                        
                        for region_name in regions_names:
                            region, message = self.find_or_create_region(region_name)
                            if region:
                                regions.append(region)
                                if message:
                                    region_messages.append(f'Строка {index + 2}: {message}')
                                    self.stdout.write(
                                        self.style.WARNING(f'Строка {index + 2}: {message}')
                                    )
                            else:
                                errors.append(f'Строка {index + 2}: {message}')
                        
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