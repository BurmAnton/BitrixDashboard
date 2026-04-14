# Документация REST API Communication

Раздел соответствует странице гида `/api/guide/?communication`.

## 1. Назначение

Эндпоинт фиксирует факт коммуникации с контрагентом: организацией и, при необходимости, конкретным контактом.

Одна запись журнала включает:

- `counterparty_organization` — ИНН организации-контрагента.
- `counterparty_contact` — id контакта контрагента (опционально).
- `our_organization` — ИНН нашей организации (`is_our_side=true`).
- `channel` — канал коммуникации.
- `occurred_at` — дата и время коммуникации.
- `result` — результат коммуникации.
- `project` — название проекта (опционально).

## 2. Эндпоинты

| Действие | Метод | URL |
|---|---|---|
| Список | `GET` | `/api/communication/` |
| Создание | `POST` | `/api/communication/` или `/api/communication/add/` |
| Частичное изменение | `PATCH` | `/api/communication/<id>/` или `/api/communication/update/` |

## 3. Каналы коммуникации

Допустимые значения поля `channel`:

- `email`
- `postal_mail`
- `letter`
- `messenger`
- `meeting`
- `call`
- `phone`

## 4. Примеры запросов

### 4.1 Создание записи

```json
{
  "counterparty_organization": "7701234567",
  "counterparty_contact": 15,
  "our_organization": "6321261206",
  "channel": "meeting",
  "occurred_at": "2026-04-14T10:30:00+03:00",
  "result": "Согласовали следующий шаг по проекту.",
  "project": "Пилот РОИВ"
}
```

### 4.2 Изменение записи (вариант `/update/`)

```json
{
  "id": 3,
  "result": "Перенесли встречу на следующую неделю.",
  "occurred_at": "2026-04-16T11:00:00+03:00"
}
```

## 5. Валидация

- `our_organization` должна ссылаться на организацию с `is_our_side=true`.
- Если передан `counterparty_contact`, контакт должен принадлежать `counterparty_organization`.
- Если указан `project`, проект должен существовать в справочнике проектов.

## 6. Фильтрация списка

Поддерживаются query-параметры:

- `organization` или `counterparty_inn` — ИНН контрагента.
- `contact_id` — id контакта.
- `our_organization` — ИНН нашей организации.
- `project` — название проекта (поиск по вхождению).
- `channel` — канал коммуникации.
- `occurred_after` / `occurred_before` — диапазон `occurred_at` (ISO datetime).

Пример:

```
/api/communication/?counterparty_inn=7701234567&channel=meeting&occurred_after=2026-04-01T00:00:00+03:00
```

## 7. Формат ответа

В ответе по каждой записи возвращаются:

- ИНН и имя организации-контрагента.
- Данные контакта (если выбран): `id`, `fio`, `position`.
- ИНН и имя нашей организации.
- `channel` и `channel_display`.
- `occurred_at`, `result`, `project`.
- `created_at`, `updated_at`.
