# Документация REST API — получение объекта

Текст соответствует странице гида `/api/guide/?get_call`. Базовый URL: `https://bitrix24.tuna-edu.ru`.

## Эндпоинты

- `GET /api/get/organization/?inn=<ИНН>` — получение организации
- `GET /api/get/program/?pk=<ID>` — получение программы

## Назначение

Получение детальной информации об организации по ИНН или об образовательной программе по первичному ключу (ID).

## Аутентификация

Требуется токен в заголовке `Authorization`.

```http
Authorization: Token <ваш_токен>
```

Токен создаётся в админ-панели Django (раздел «Токены»). Доступ к гиду API обычно ограничен.

## Параметры запроса

| Эндпоинт | Параметр | Тип | Описание |
|----------|----------|-----|----------|
| `/organization/` | `inn` | string | ИНН организации (10 или 12 цифр) |
| `/program/` | `pk` | integer | Первичный ключ (ID) программы |

## Примеры запросов

### cURL

**Организация по ИНН:**

```bash
curl -X GET "https://bitrix24.tuna-edu.ru/api/get/organization/?inn=7707083893" \
  -H "Authorization: Token 4a8389aa7f015d3a68e44e3f4bae94d63c7ac097"
```

**Программа по PK:**

```bash
curl -X GET "https://bitrix24.tuna-edu.ru/api/get/program/?pk=42" \
  -H "Authorization: Token 4a8389aa7f015d3a68e44e3f4bae94d63c7ac097"
```

### JavaScript (fetch)

**Организация:**

```javascript
fetch('/api/get/organization/?inn=7707083893', {
  headers: { 'Authorization': 'Token 4a8389aa7f015d3a68e44e3f4bae94d63c7ac097' }
})
.then(response => response.json())
.then(data => console.log(data));
```

**Программа:**

```javascript
fetch('/api/get/program/?pk=42', {
  headers: { 'Authorization': 'Token 4a8389aa7f015d3a68e44e3f4bae94d63c7ac097' }
})
.then(response => response.json())
.then(data => console.log(data));
```

### Python (requests)

**Организация:**

```python
import requests
headers = {'Authorization': 'Token 4a8389aa7f015d3a68e44e3f4bae94d63c7ac097'}
params = {'inn': '7707083893'}
response = requests.get('https://bitrix24.tuna-edu.ru/api/get/organization/', headers=headers, params=params)
print(response.json())
```

**Программа:**

```python
import requests
headers = {'Authorization': 'Token 4a8389aa7f015d3a68e44e3f4bae94d63c7ac097'}
params = {'pk': 42}
response = requests.get('https://bitrix24.tuna-edu.ru/api/get/program/', headers=headers, params=params)
print(response.json())
```

## Примеры успешных ответов (HTTP 200)

**Организация:**

```json
{
  "inn": "7707083893",
  "name": "Сбербанк",
  "full_name": "Публичное акционерное общество 'Сбербанк России'",
  "type": "ПАО",
  "region": "Москва",
  "federal_company": true,
  "fed_district": "Центральный",
  "prof_activity": "Банковская деятельность",
  "projects": [{"id": 1, "name": "Цифровая трансформация"}],
  "is_active": true,
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-02-20T14:30:00Z"
}
```

**Программа:**

```json
{
  "name": "Программа повышения квалификации",
  "academic_hours": 72,
  "program_type": "PROF",
  "study_form": "FT",
  "DOT": true,
  "description": "Описание программы...",
  "duration": "14",
  "final_attestation": "2",
  "activities": [{"id": 1, "name": "Лекция"}],
  "sections": [
    {
      "order": 1,
      "name": "Раздел 1",
      "lecture_hours": 10,
      "practice_hours": 8,
      "selfstudy_hours": 6,
      "consultation_hours": 2,
      "dot_hours": 4,
      "workload": 30,
      "attestation_form": "Тест",
      "description": "Описание раздела",
      "topics": [
        {
          "order": 1,
          "name": "Тема 1",
          "lecture_hours": 4,
          "practice_hours": 4,
          "selfstudy_hours": 2,
          "consultation_hours": 1,
          "dot_hours": 2,
          "workload": 13,
          "attestation_form": "Опрос",
          "description": "Описание темы"
        }
      ]
    }
  ]
}
```

## Возможные ошибки

| Код | Эндпоинт | Описание | Пример ответа |
|-----|----------|----------|----------------|
| 400 | `/organization/` | Не передан ИНН | `{"error": "ИНН обязателен", "usage": "/api/get/organization/?inn=<ИНН>"}` |
| 400 | `/program/` | Не передан pk | `{"error": "Ключ обязателен", "usage": "/api/get/program/?pk=<pk>"}` |
| 401 | оба | Отсутствует или неверный токен | `{"detail": "Authentication credentials were not provided."}` |
| 403 | оба | Недостаточно прав | `{"detail": "You do not have permission to perform this action."}` |
| 404 | `/organization/` | Организация не найдена | `{"error": "Организация с ИНН 1234567890 не найдена"}` |
| 404 | `/program/` | Программа не найдена | `{"error": "Программа по ключу 999 не найдена"}` |

## Примечания

- **Организация:** ИНН — строка из цифр. Поле `projects` может быть пустым массивом. `fed_district` вычисляется автоматически.
- **Программа:** `pk` — числовой ID записи в БД `EducationProgram`. Поле `sections` содержит вложенные разделы и темы; при отсутствии разделов — пустой массив.
- Оба эндпоинта требуют аутентификации: `Authorization: Token <ваш_токен>`.
