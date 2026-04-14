#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Добавляет все РОИВ (education_planner) в Organization (contact_management) с типом РОИВ.
ИНН из minobraz_regiony_rf_inn.xlsx при совпадении; иначе ROIV-<id>.
Запуск без Django: python sync_roiv_to_organizations.py
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
}


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
    xlsx_path = os.path.join(base, 'minobraz_regiony_rf_inn.xlsx')
    inn_map = {}
    if os.path.isfile(xlsx_path):
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        for row in (rows[3:] if len(rows) > 3 else []):
            if not row or len(row) < 3:
                continue
            region_sheet = (row[0] or '').strip()
            organ = (row[1] or '').strip()
            inn = norm_inn(row[2])
            if not region_sheet or not organ or not inn:
                continue
            region_name = REGION_ALIASES.get(region_sheet, region_sheet)
            inn_map[(region_name, organ)] = inn
        print(f'ИНН из xlsx: {len(inn_map)} записей')

    conn = psycopg2.connect(
        dbname=os.environ.get('DB_NAME', 'bitrix24_db'),
        user=os.environ.get('DB_USER', 'bitrix_admin'),
        password=os.environ.get('DB_PASSWORD', ''),
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '5432'),
    )
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("SELECT id FROM contact_management_organizationtype WHERE name = 'РОИВ'")
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO contact_management_organizationtype (name) VALUES ('РОИВ') RETURNING id")
        type_id = cur.fetchone()[0]
    else:
        type_id = row[0]

    cur.execute("SELECT id FROM education_planner_profactivity WHERE name = 'Образование и наука'")
    activity_row = cur.fetchone()
    activity_id = activity_row[0] if activity_row else None

    cur.execute("""
        SELECT r.id, r.name, r.full_name, r.region_id, r.is_active, reg.name AS region_name
        FROM education_planner_roiv r
        LEFT JOIN education_planner_region reg ON reg.id = r.region_id
        WHERE r.is_active = true
        ORDER BY r.id
    """)
    roivs = cur.fetchall()

    created = 0
    updated = 0
    for (roiv_id, roiv_name, full_name, region_ep_id, is_active, region_name) in roivs:
        roiv_name = roiv_name or ''
        full_name = (full_name or roiv_name or '').strip() or roiv_name
        region_name = region_name or ''
        inn = inn_map.get((region_name, roiv_name)) or inn_map.get(roiv_name) or f'ROIV-{roiv_id}'
        inn = str(inn).strip()
        if not inn:
            inn = f'ROIV-{roiv_id}'

        cur.execute("SELECT id FROM contact_management_region WHERE name = %s", (region_name,))
        r = cur.fetchone()
        cm_region_id = r[0] if r else None

        cur.execute("SELECT id, inn FROM contact_management_organization WHERE roiv_id = %s", (roiv_id,))
        existing = cur.fetchone()
        if existing:
            org_id, old_inn = existing[0], existing[1]
            cur.execute("SELECT 1 FROM contact_management_organization WHERE inn = %s AND id != %s", (inn, org_id))
            if cur.fetchone():
                inn = f'ROIV-{roiv_id}'
            cur.execute("""
                UPDATE contact_management_organization
                SET inn = %s, type_id = %s, region_id = %s, name = %s, full_name = %s, is_active = %s, updated_at = NOW()
                WHERE id = %s
            """, (inn, type_id, cm_region_id, roiv_name, full_name, bool(is_active), org_id))
            updated += 1
        else:
            cur.execute("SELECT 1 FROM contact_management_organization WHERE inn = %s", (inn,))
            if cur.fetchone():
                inn = f'ROIV-{roiv_id}'
            cur.execute("""
                INSERT INTO contact_management_organization
                (inn, name, full_name, type_id, roiv_id, region_id, federal_company, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, false, %s, NOW(), NOW())
                RETURNING id
            """, (inn, roiv_name, full_name, type_id, roiv_id, cm_region_id, bool(is_active)))
            org_id = cur.fetchone()[0]
            created += 1

        if activity_id:
            cur.execute("""
                SELECT 1 FROM contact_management_organization_prof_activity
                WHERE organization_id = %s AND profactivity_id = %s
            """, (org_id, activity_id))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO contact_management_organization_prof_activity (organization_id, profactivity_id)
                    VALUES (%s, %s)
                """, (org_id, activity_id))

    conn.commit()
    cur.close()
    conn.close()
    print(f'Готово. Создано: {created}, обновлено: {updated}')


if __name__ == '__main__':
    main()
