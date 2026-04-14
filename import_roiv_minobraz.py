#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Импорт РОИВ из minobraz_regiony_rf_inn.xlsx со сферой «Образование и наука»."""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import openpyxl
import psycopg2

# Регион из файла -> название в education_planner_region (где отличается)
REGION_ALIASES = {
    'Кемеровская область - Кузбасс': 'Кемеровская область',
    'Республика Северная Осетия - Алания': 'Республика Северная Осетия — Алания',
    'Ханты-Мансийский автономный округ – Югра': 'Ханты-Мансийский автономный округ — Югра',
}

ACTIVITY_NAME = 'Образование и наука'


def main():
    path = os.path.join(os.path.dirname(__file__), 'minobraz_regiony_rf_inn.xlsx')
    if not os.path.isfile(path):
        print('Файл не найден:', path)
        sys.exit(1)

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # Заголовок в строке 2: Регион, Орган в сфере образования, ИНН, ...
    if len(rows) < 3:
        print('Мало строк в файле.')
        sys.exit(1)

    conn = psycopg2.connect(
        dbname=os.environ.get('DB_NAME', 'bitrix24_db'),
        user=os.environ.get('DB_USER', 'bitrix_admin'),
        password=os.environ.get('DB_PASSWORD', ''),
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '5432'),
    )
    conn.autocommit = False
    cur = conn.cursor()

    # Сфера деятельности
    cur.execute(
        "SELECT id FROM education_planner_profactivity WHERE name = %s",
        (ACTIVITY_NAME,),
    )
    row_act = cur.fetchone()
    if not row_act:
        cur.execute(
            "INSERT INTO education_planner_profactivity (name, description, created_at, updated_at) VALUES (%s, '', NOW(), NOW()) RETURNING id",
            (ACTIVITY_NAME,),
        )
        activity_id = cur.fetchone()[0]
    else:
        activity_id = row_act[0]

    created = 0
    updated_activity = 0
    skipped = []

    for row in rows[3:]:
        if not row or len(row) < 3:
            continue
        region_name_sheet = (row[0] or '').strip()
        organ_name = (row[1] or '').strip()
        if not region_name_sheet or not organ_name:
            continue
        region_name = REGION_ALIASES.get(region_name_sheet, region_name_sheet)

        cur.execute(
            "SELECT id FROM education_planner_region WHERE name = %s",
            (region_name,),
        )
        r = cur.fetchone()
        if not r:
            skipped.append(region_name_sheet)
            continue
        region_id = r[0]

        cur.execute(
            "SELECT id FROM education_planner_roiv WHERE name = %s AND region_id = %s",
            (organ_name, region_id),
        )
        roiv_row = cur.fetchone()
        if roiv_row:
            roiv_id = roiv_row[0]
        else:
            cur.execute(
                """INSERT INTO education_planner_roiv (name, region_id, full_name, is_active, created_at, updated_at)
                   VALUES (%s, %s, %s, true, NOW(), NOW()) RETURNING id""",
                (organ_name, region_id, organ_name),
            )
            roiv_id = cur.fetchone()[0]
            created += 1

        cur.execute(
            "SELECT 1 FROM education_planner_roiv_prof_activity WHERE roiv_id = %s AND profactivity_id = %s",
            (roiv_id, activity_id),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO education_planner_roiv_prof_activity (roiv_id, profactivity_id) VALUES (%s, %s)",
                (roiv_id, activity_id),
            )
            updated_activity += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f'Создано РОИВ: {created}, добавлена сфера «{ACTIVITY_NAME}»: {updated_activity}.')
    if skipped:
        print('Нет региона в БД (пропущено):', ', '.join(skipped[:15]), '...' if len(skipped) > 15 else '')


if __name__ == '__main__':
    main()
