# -*- coding: utf-8 -*-
"""
Создаёт записи Organization (тип РОИВ) для всех РОИВ из education_planner.
ИНН берётся из minobraz_regiony_rf_inn.xlsx при совпадении региона и названия; иначе — ROIV-<id>.
"""
import os
from django.core.management.base import BaseCommand

# Регион из xlsx -> название в БД (education_planner / contact_management)
REGION_ALIASES = {
    'Кемеровская область - Кузбасс': 'Кемеровская область',
    'Республика Северная Осетия - Алания': 'Республика Северная Осетия — Алания',
    'Ханты-Мансийский автономный округ – Югра': 'Ханты-Мансийский автономный округ — Югра',
}


class Command(BaseCommand):
    help = 'Добавляет все РОИВ (education_planner) в Organization (contact_management) с типом РОИВ'

    def add_arguments(self, parser):
        parser.add_argument(
            '--xlsx',
            type=str,
            default='minobraz_regiony_rf_inn.xlsx',
            help='Путь к xlsx с колонками: Регион, Орган, ИНН (для подстановки ИНН)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать, что будет сделано',
        )

    def handle(self, *args, **options):
        from education_planner.models import ROIV
        from contact_management.models import Organization, OrganizationType, Region
        from education_planner.models import ProfActivity

        # Карта (region_name, organ_name) -> inn из xlsx
        inn_map = {}
        xlsx_path = options.get('xlsx')
        if xlsx_path and os.path.isfile(xlsx_path):
            import openpyxl
            wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
            for row in (rows[3:] if len(rows) > 3 else []):
                if not row or len(row) < 3:
                    continue
                region_sheet = (row[0] or '').strip()
                organ = (row[1] or '').strip()
                inn_raw = row[2]
                if not region_sheet or not organ:
                    continue
                region_name = REGION_ALIASES.get(region_sheet, region_sheet)
                inn = str(inn_raw).strip() if inn_raw is not None else ''
                if inn and inn.replace('.', '').replace(',', '').isdigit():
                    inn = str(int(float(inn.replace(',', '.'))))
                elif inn:
                    inn = ''.join(c for c in inn if c.isdigit())[:12] or inn
                if inn:
                    inn_map[(region_name, organ)] = inn
            self.stdout.write(f'Загружено ИНН из xlsx: {len(inn_map)} записей')

        type_roiv, _ = OrganizationType.objects.get_or_create(name='РОИВ')
        activity_edu = ProfActivity.objects.filter(name='Образование и наука').first()

        roivs = ROIV.objects.filter(is_active=True).select_related('region')
        created = 0
        updated = 0
        skipped = 0
        dry_run = options.get('dry_run', False)

        for roiv in roivs:
            region_name = roiv.region.name if roiv.region_id else None
            inn = inn_map.get((region_name, roiv.name)) or inn_map.get(roiv.name) or f'ROIV-{roiv.id}'
            inn = str(inn).strip()
            if not inn:
                inn = f'ROIV-{roiv.id}'

            cm_region = None
            if region_name:
                cm_region = Region.objects.filter(name=region_name).first()

            existing = Organization.objects.filter(roiv=roiv).first()
            if existing:
                if not dry_run:
                    changed = False
                    if existing.inn != inn and not Organization.objects.filter(inn=inn).exclude(pk=existing.pk).exists():
                        existing.inn = inn
                        changed = True
                    if existing.type_id != type_roiv.pk:
                        existing.type = type_roiv
                        changed = True
                    if existing.region_id != (cm_region.pk if cm_region else None):
                        existing.region = cm_region
                        changed = True
                    if existing.name != roiv.name or (existing.full_name or '') != (roiv.full_name or roiv.name or ''):
                        existing.name = roiv.name
                        existing.full_name = roiv.full_name or roiv.name or ''
                        changed = True
                    if changed:
                        existing.save()
                        if activity_edu and existing.type_id == type_roiv.pk:
                            existing.prof_activity.add(activity_edu)
                        updated += 1
            else:
                if Organization.objects.filter(inn=inn).exists():
                    inn = f'ROIV-{roiv.id}'
                if not dry_run:
                    org = Organization.objects.create(
                        inn=inn,
                        type=type_roiv,
                        roiv=roiv,
                        region=cm_region,
                        name=roiv.name,
                        full_name=roiv.full_name or roiv.name or '',
                        federal_company=False,
                        is_active=roiv.is_active,
                    )
                    if activity_edu:
                        org.prof_activity.add(activity_edu)
                    created += 1
                else:
                    created += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f'Dry-run: создано бы {created}, обновлено бы {updated}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Готово. Создано организаций: {created}, обновлено: {updated}'))
