#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импорт РОИВ + Organization из minkult_regiony_rf_inn.xlsx со сферой «Культура».
Создаёт РОИВ (если нет), привязывает сферу, создаёт/обновляет Organization с типом РОИВ и ИНН.
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import openpyxl
import psycopg2

REGION_ALIASES = {
    'Кемеровская область - Кузбасс': 'Кемеровская область',
    'Республика Северная Осетия - Алания': 'Республика Северная Осетия — Алания',
    'Ханты-Мансийский автономный округ – Югра': 'Ханты-Мансийский автономный округ — Югра',
    'Ханты-Мансийский автономный округ - Югра': 'Ханты-Мансийский автономный округ — Югра',
}

ACTIVITY_NAME = 'Культура'


def norm_inn(v):
    if v is None:
        return ''
    s = str(v).strip()
    if s.replace('.', '').replace(',', '').isdigit():
        try:
            return str(int(float(s.replace(',', '.'))))
        except Exception:
            pass
    return ''.join(c for c in s if c.isdigit())[:12] or s


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, 'minkult_regiony_rf_inn.xlsx')
    if not os.path.isfile(path):
        print('Файл не найден:', path)
        sys.exit(1)

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
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
    cur.execute("SELECT id FROM education_planner_profactivity WHERE name = %s", (ACTIVITY_NAME,))
    row_act = cur.fetchone()
    if not row_act:
        cur.execute(
            "INSERT INTO education_planner_profactivity (name, description, created_at, updated_at) VALUES (%s, '', NOW(), NOW()) RETURNING id",
            (ACTIVITY_NAME,),
        )
        activity_id = cur.fetchone()[0]
    else:
        activity_id = row_act[0]

    # Тип организации РОИВ
    cur.execute("SELECT id FROM contact_management_organizationtype WHERE name = 'РОИВ'")
    type_roiv = cur.fetchone()
    if not type_roiv:
        cur.execute("INSERT INTO contact_management_organizationtype (name) VALUES ('РОИВ') RETURNING id")
        type_id = cur.fetchone()[0]
    else:
        type_id = type_roiv[0]

    created_roiv = 0
    created_org = 0
    updated_org = 0
    skipped = []

    for row in rows[3:]:
        if not row or len(row) < 3:
            continue
        region_name_sheet = (row[0] or '').strip()
        organ_name = (row[1] or '').strip()
        inn = norm_inn(row[2])
        if not region_name_sheet or not organ_name:
            continue
        region_name = REGION_ALIASES.get(region_name_sheet, region_name_sheet)

        cur.execute("SELECT id FROM education_planner_region WHERE name = %s", (region_name,))
        r = cur.fetchone()
        if not r:
            skipped.append(region_name_sheet)
            continue
        region_ep_id = r[0]

        cur.execute(
            "SELECT id FROM education_planner_roiv WHERE name = %s AND region_id = %s",
            (organ_name, region_ep_id),
        )
        roiv_row = cur.fetchone()
        if roiv_row:
            roiv_id = roiv_row[0]
        else:
            cur.execute(
                """INSERT INTO education_planner_roiv (name, region_id, full_name, is_active, created_at, updated_at)
                   VALUES (%s, %s, %s, true, NOW(), NOW()) RETURNING id""",
                (organ_name, region_ep_id, organ_name),
            )
            roiv_id = cur.fetchone()[0]
            created_roiv += 1

        cur.execute(
            "SELECT 1 FROM education_planner_roiv_prof_activity WHERE roiv_id = %s AND profactivity_id = %s",
            (roiv_id, activity_id),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO education_planner_roiv_prof_activity (roiv_id, profactivity_id) VALUES (%s, %s)",
                (roiv_id, activity_id),
            )

        cur.execute("SELECT id FROM contact_management_region WHERE name = %s", (region_name,))
        cm_reg = cur.fetchone()
        cm_region_id = cm_reg[0] if cm_reg else None

        if not inn:
            inn = f'ROIV-{roiv_id}'

        cur.execute("SELECT id FROM contact_management_organization WHERE roiv_id = %s", (roiv_id,))
        existing_org = cur.fetchone()
        if existing_org:
            org_id = existing_org[0]
            cur.execute("SELECT 1 FROM contact_management_organization WHERE inn = %s AND id != %s", (inn, org_id))
            if cur.fetchone():
                inn = f'ROIV-{roiv_id}'
            cur.execute("""
                UPDATE contact_management_organization
                SET inn = %s, type_id = %s, region_id = %s, name = %s, full_name = %s, is_active = true, updated_at = NOW()
                WHERE id = %s
            """, (inn, type_id, cm_region_id, organ_name, organ_name, org_id))
            updated_org += 1
        else:
            cur.execute("SELECT 1 FROM contact_management_organization WHERE inn = %s", (inn,))
            if cur.fetchone():
                inn = f'ROIV-{roiv_id}'
            cur.execute("""
                INSERT INTO contact_management_organization
                (inn, name, full_name, type_id, roiv_id, region_id, federal_company, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, false, true, NOW(), NOW())
                RETURNING id
            """, (inn, organ_name, organ_name, type_id, roiv_id, cm_region_id))
            org_id = cur.fetchone()[0]
            created_org += 1

        cur.execute(
            "SELECT 1 FROM contact_management_organization_prof_activity WHERE organization_id = %s AND profactivity_id = %s",
            (org_id, activity_id),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO contact_management_organization_prof_activity (organization_id, profactivity_id) VALUES (%s, %s)",
                (org_id, activity_id),
            )

    conn.commit()
    cur.close()
    conn.close()

    print(f'РОИВ: создано {created_roiv}. Организации: создано {created_org}, обновлено {updated_org}. Сфера «{ACTIVITY_NAME}» привязана.')
    if skipped:
        print('Нет региона в БД (пропущено):', ', '.join(skipped[:20]), '...' if len(skipped) > 20 else '')


if __name__ == '__main__':
    main()
