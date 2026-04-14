#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Добавляет все федеральные округа РФ в contact_management_federaldistrict.
Существующие не дублируются. После этого API /contacts/api/get_all/fed_district/ возвращает полный список.
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import psycopg2

# Все федеральные округа РФ (официальные названия)
FEDERAL_DISTRICTS = [
    "Центральный федеральный округ",
    "Северо-Западный федеральный округ",
    "Южный федеральный округ",
    "Северо-Кавказский федеральный округ",
    "Приволжский федеральный округ",
    "Уральский федеральный округ",
    "Сибирский федеральный округ",
    "Дальневосточный федеральный округ",
    "Новые территории",  # новые субъекты
]


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

    cur.execute("SELECT name FROM contact_management_federaldistrict")
    existing = {r[0] for r in cur.fetchall()}

    added = 0
    for name in FEDERAL_DISTRICTS:
        if name in existing:
            continue
        cur.execute(
            "INSERT INTO contact_management_federaldistrict (name) VALUES (%s)",
            (name,),
        )
        added += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f'Добавлено федеральных округов: {added}. Всего в списке API: {len(FEDERAL_DISTRICTS)}.')


if __name__ == '__main__':
    main()
