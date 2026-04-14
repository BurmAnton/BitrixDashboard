#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Однократный импорт кодов регионов из xlsx (без Django)."""
import os
import sys

# .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import openpyxl
import psycopg2
from psycopg2.extras import execute_values

# Те же алиасы, что в update_region_codes
NAME_ALIASES = {
    'Москва': 'город Москва',
    'Санкт-Петербург': 'город Санкт-Петербург',
    'Республика Крым': 'Крым',
    'Чувашская Республика (Чувашия)': 'Чувашская Республика - Чувашия',
    'Чеченская республика': 'Чеченская Республика',
    'Республика Адыгея (Адыгея)': 'Республика Адыгея',
    'Республика Татарстан (Татарстан)': 'Республика Татарстан',
}


def normalize_code(raw):
    if raw is None:
        return ''
    if isinstance(raw, (int, float)):
        return str(int(raw))
    s = str(raw).strip()
    if ',' in s:
        s = s.split(',')[0].strip()
    if s.replace('.', '').isdigit():
        try:
            return str(int(float(s)))
        except (ValueError, TypeError):
            pass
    return s


def resolve_name(name_from_sheet):
    name = (name_from_sheet or '').strip()
    if not name:
        return None
    return NAME_ALIASES.get(name, name)


def main():
    path = os.path.join(os.path.dirname(__file__), 'Untitled spreadsheet (7).xlsx')
    if not os.path.isfile(path):
        print(f'Файл не найден: {path}')
        sys.exit(1)

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows or len(rows) < 2:
        print('Нет данных в файле.')
        sys.exit(1)

    # колонка 0 = код, 1 = субъект
    updates = []
    for row in rows[1:]:
        if not row or len(row) < 2:
            continue
        code = normalize_code(row[0])
        if not code:
            continue
        name = resolve_name(row[1])
        if not name:
            continue
        updates.append((code, name))

    if not updates:
        print('Нет строк для обновления.')
        sys.exit(0)

    conn = psycopg2.connect(
        dbname=os.environ.get('DB_NAME', 'bitrix24_db'),
        user=os.environ.get('DB_USER', 'bitrix_admin'),
        password=os.environ.get('DB_PASSWORD', ''),
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '5432'),
    )
    conn.autocommit = False
    cur = conn.cursor()

    updated_edu = 0
    updated_contact = 0
    for code, name in updates:
        cur.execute(
            "UPDATE education_planner_region SET code = %s WHERE name = %s AND (code IS NULL OR code != %s)",
            (code, name, code),
        )
        if cur.rowcount:
            updated_edu += 1
        cur.execute(
            "UPDATE contact_management_region SET code = %s WHERE name = %s AND (code IS NULL OR code != %s)",
            (code, name, code),
        )
        if cur.rowcount:
            updated_contact += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f'Готово. Обновлено: education_planner — {updated_edu}, contact_management — {updated_contact}')


if __name__ == '__main__':
    main()
