#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1) Дополняет contact_management_region всеми регионами из education_planner_region (по названию).
2) Заполняет region для всех организаций, привязанных к РОИВ, по региону РОИВ.
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import psycopg2

# Название в education_planner -> название в contact_management (если уже есть под другим именем)
NAME_TO_CM = {
    'Москва': 'г. Москва',
    'город Москва': 'г. Москва',
    'Санкт-Петербург': 'г. Санкт-Петербург',
    'город Санкт-Петербург': 'г. Санкт-Петербург',
    'Республика Крым': 'Крым',
    'Чувашская Республика': 'Чувашская Республика - Чувашия',
}


def main():
    conn = psycopg2.connect(
        dbname=os.environ.get('DB_NAME', 'bitrix24_db'),
        user=os.environ.get('DB_USER', 'bitrix_admin'),
        password=os.environ.get('DB_PASSWORD', ''),
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '5432'),
    )
    conn.autocommit = False
    cur = conn.cursor()

    # 1) Добавить в contact_management все регионы из education_planner (по названию)
    cur.execute("SELECT name, code FROM education_planner_region ORDER BY name")
    ep_regions = cur.fetchall()
    added = 0
    for name_ep, code in ep_regions:
        cur.execute("SELECT 1 FROM contact_management_region WHERE name = %s", (name_ep,))
        if cur.fetchone():
            continue
        cur.execute(
            "INSERT INTO contact_management_region (name, code, is_active, created_at, updated_at) VALUES (%s, %s, true, NOW(), NOW())",
            (name_ep, code or ''),
        )
        added += 1
    print(f'Добавлено регионов в contact_management: {added}')

    # 3) Заполнить organization.region_id по roiv.region (по имени региона)
    cur.execute("""
        SELECT o.id, o.region_id, r_ep.name AS region_name
        FROM contact_management_organization o
        JOIN education_planner_roiv roiv ON roiv.id = o.roiv_id
        JOIN education_planner_region r_ep ON r_ep.id = roiv.region_id
        WHERE o.roiv_id IS NOT NULL
    """)
    rows = cur.fetchall()

    updated = 0
    skipped = 0
    for org_id, current_region_id, region_name in rows:
        name_cm = NAME_TO_CM.get(region_name, region_name)
        cur.execute("SELECT id FROM contact_management_region WHERE name = %s OR name = %s", (region_name, name_cm))
        r = cur.fetchone()
        if not r:
            skipped += 1
            continue
        cm_region_id = r[0]
        if current_region_id != cm_region_id:
            cur.execute(
                "UPDATE contact_management_organization SET region_id = %s, updated_at = NOW() WHERE id = %s",
                (cm_region_id, org_id),
            )
            updated += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f'Обновлено организаций (регион по РОИВ): {updated}. Без совпадения региона: {skipped}.')


if __name__ == '__main__':
    main()
