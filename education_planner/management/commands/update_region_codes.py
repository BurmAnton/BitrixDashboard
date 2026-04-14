# -*- coding: utf-8 -*-
"""
Импорт кодов регионов из xlsx.
Берёт первый код, если в ячейке несколько через запятую.
Названия регионов не меняются; сопоставление по имени (с алиасами где не совпадает 1:1).
"""
import os
from django.core.management.base import BaseCommand

# Канонические названия из crm_connector.REGION_CHOICES (название не меняем)
CANONICAL_NAMES = [
    'Амурская область',
    'Архангельская область',
    'Астраханская область',
    'Белгородская область',
    'Брянская область',
    'Владимирская область',
    'Волгоградская область',
    'Вологодская область',
    'Воронежская область',
    'Донецкая Народная Республика',
    'Еврейская автономная область',
    'Забайкальский край',
    'Запорожская область',
    'Ивановская область',
    'Иркутская область',
    'Кабардино-Балкарская Республика',
    'Калининградская область',
    'Калужская область',
    'Камчатский край',
    'Карачаево-Черкесская Республика',
    'Кемеровская область',
    'Кировская область',
    'Костромская область',
    'Краснодарский край',
    'Красноярский край',
    'Крым',
    'Курганская область',
    'Курская область',
    'Ленинградская область',
    'Липецкая область',
    'Луганская Народная Республика',
    'Магаданская область',
    'город Москва',
    'Московская область',
    'Мурманская область',
    'Ненецкий автономный округ',
    'Нижегородская область',
    'Новгородская область',
    'Новосибирская область',
    'Омская область',
    'Оренбургская область',
    'Орловская область',
    'Пензенская область',
    'Пермский край',
    'Приморский край',
    'Псковская область',
    'Республика Адыгея',
    'Республика Алтай',
    'Республика Башкортостан',
    'Республика Бурятия',
    'Республика Дагестан',
    'Республика Ингушетия',
    'Республика Калмыкия',
    'Республика Карелия',
    'Республика Коми',
    'Республика Марий Эл',
    'Республика Мордовия',
    'Республика Саха (Якутия)',
    'Республика Северная Осетия — Алания',
    'Республика Татарстан',
    'Республика Тыва',
    'Республика Хакасия',
    'Ростовская область',
    'Рязанская область',
    'Самарская область',
    'город Санкт-Петербург',
    'Саратовская область',
    'Сахалинская область',
    'Свердловская область',
    'Севастополь',
    'Смоленская область',
    'Ставропольский край',
    'Тамбовская область',
    'Тверская область',
    'Томская область',
    'Тульская область',
    'Тюменская область',
    'Удмуртская Республика',
    'Ульяновская область',
    'Хабаровский край',
    'Ханты-Мансийский автономный округ — Югра',
    'Херсонская область',
    'Челябинская область',
    'Чеченская Республика',
    'Чувашская Республика - Чувашия',
    'Чукотский автономный округ',
    'Ямало-Ненецкий автономный округ',
    'Ярославская область',
]

# Сопоставление: вариант из таблицы -> каноническое название (1:1 где не совпадает)
NAME_ALIASES = {
    'Москва': 'город Москва',
    'г. Москва': 'город Москва',
    'Санкт-Петербург': 'город Санкт-Петербург',
    'СПб': 'город Санкт-Петербург',
    'г. Санкт-Петербург': 'город Санкт-Петербург',
    'Республика Крым': 'Крым',
    'Чувашская Республика': 'Чувашская Республика - Чувашия',
    'Чувашская Республика (Чувашия)': 'Чувашская Республика - Чувашия',
    'Республика Северная Осетия - Алания': 'Республика Северная Осетия — Алания',
    'Республика Северная Осетия – Алания': 'Республика Северная Осетия — Алания',
    'Ханты-Мансийский автономный округ - Югра': 'Ханты-Мансийский автономный округ — Югра',
    'Ханты-Мансийский АО — Югра': 'Ханты-Мансийский автономный округ — Югра',
    'Ямало-Ненецкий АО': 'Ямало-Ненецкий автономный округ',
    'Ненецкий АО': 'Ненецкий автономный округ',
    'Чукотский АО': 'Чукотский автономный округ',
    'Еврейская АО': 'Еврейская автономная область',
    'Чеченская республика': 'Чеченская Республика',
    'Республика Адыгея (Адыгея)': 'Республика Адыгея',
    'Республика Татарстан (Татарстан)': 'Республика Татарстан',
}


def normalize_code(raw):
    """Берём первый код, если несколько через запятую. Числа без десятичной части."""
    if raw is None:
        return ''
    if isinstance(raw, (int, float)):
        return str(int(raw))
    s = str(raw).strip()
    if ',' in s:
        s = s.split(',')[0].strip()
    # убрать .0 у целых
    if s.replace('.', '').isdigit():
        try:
            return str(int(float(s)))
        except (ValueError, TypeError):
            pass
    return s


def resolve_region_name(name_from_sheet):
    """Сопоставить название из таблицы с каноническим (1:1)."""
    name = (name_from_sheet or '').strip()
    if not name:
        return None
    if name in CANONICAL_NAMES:
        return name
    return NAME_ALIASES.get(name, name)


class Command(BaseCommand):
    help = (
        'Заводит коды регионов из xlsx: первый код при нескольких через запятую, '
        'сопоставление названий 1:1 (название не меняется).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'file',
            type=str,
            help='Путь к xlsx-файлу (колонки: название региона, код/коды)',
        )
        parser.add_argument(
            '--name-col',
            type=int,
            default=None,
            help='Номер колонки с названием (0-based). По умолчанию — авто по заголовку или 0',
        )
        parser.add_argument(
            '--code-col',
            type=int,
            default=None,
            help='Номер колонки с кодом (0-based). По умолчанию — авто по заголовку или 1',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать, что будет обновлено, без записи в БД',
        )

    def handle(self, *args, **options):
        import openpyxl

        path = options['file']
        if not os.path.isfile(path):
            self.stdout.write(self.style.ERROR(f'Файл не найден: {path}'))
            return

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            self.stdout.write(self.style.ERROR('Файл пустой или без данных.'))
            return

        header = [str(c).strip().lower() if c is not None else '' for c in rows[0]]
        data_rows = rows[1:]

        # Колонки: название и код
        name_col = options.get('name_col')
        code_col = options.get('code_col')

        if name_col is None:
            for i, h in enumerate(header):
                if any(x in h for x in ('название', 'регион', 'region', 'name', 'субъект')):
                    name_col = i
                    break
            if name_col is None:
                name_col = 0
        if code_col is None:
            for i, h in enumerate(header):
                if any(x in h for x in ('код', 'code')):
                    code_col = i
                    break
            if code_col is None:
                code_col = 1 if name_col == 0 else 0
        # Файл «Код» | «Субъект Российской Федерации»: код=0, название=1
        if code_col == name_col:
            code_col, name_col = 0, 1

        self.stdout.write(f'Колонка названия: {name_col}, колонка кода: {code_col}')

        from education_planner.models import Region as EduRegion
        from education_planner.models import RegionAltNames
        from contact_management.models import Region as ContactRegion

        updated_edu = 0
        updated_contact = 0
        skipped = []
        dry_run = options.get('dry_run', False)

        for row in data_rows:
            if not row:
                continue
            name_raw = row[name_col] if name_col < len(row) else None
            code_raw = row[code_col] if code_col < len(row) else None
            code = normalize_code(code_raw)
            if not code:
                continue
            canonical = resolve_region_name(name_raw)
            if not canonical:
                continue

            # Обновить education_planner.Region (по имени или псевдониму)
            region_edu = EduRegion.objects.filter(name=canonical).first()
            if not region_edu:
                alt = RegionAltNames.objects.filter(name=canonical).select_related('region').first()
                if alt:
                    region_edu = alt.region
            if region_edu:
                if region_edu.code != code:
                    if not dry_run:
                        region_edu.code = code
                        region_edu.save()
                    updated_edu += 1
                    self.stdout.write(f'  [education_planner] {canonical}: код {code}')
            else:
                skipped.append((name_raw, canonical, code))

            # Обновить contact_management.Region по тому же каноническому имени
            region_contact = ContactRegion.objects.filter(name=canonical).first()
            if region_contact and region_contact.code != code:
                if not dry_run:
                    region_contact.code = code
                    region_contact.save()
                updated_contact += 1
                if updated_contact == 1 or (updated_contact <= 3):
                    self.stdout.write(f'  [contact_management] {canonical}: код {code}')

        wb.close()

        if skipped:
            self.stdout.write(self.style.WARNING(
                f'Не найдены в БД (регион не создаётся, только коды обновляются): {len(skipped)}'
            ))
            for name_raw, canon, c in skipped[:15]:
                self.stdout.write(f'    — "{name_raw}" -> {canon} (код {c})')
            if len(skipped) > 15:
                self.stdout.write(f'    ... и ещё {len(skipped) - 15}')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Dry-run: обновлено бы education_planner: {updated_edu}, contact_management: {updated_contact}'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Готово. Обновлено кодов: education_planner — {updated_edu}, contact_management — {updated_contact}'
            ))
