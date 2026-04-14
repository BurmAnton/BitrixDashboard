# Документация REST API — образовательные программы

Текст соответствует странице гида `/api/guide/?program`. Базовый URL: `https://bitrix24.tuna-edu.ru`.

## Эндпоинт

`GET /api/program/`

## Назначение

Получение списка образовательных программ с возможностью фильтрации по названию, типу, форме обучения и использованию ДОТ.

## Аутентификация

Требуется токен в заголовке:

```http
Authorization: Token <ваш_токен>
```

## Параметры фильтрации

| Параметр | Тип | Описание | Пример |
|----------|-----|----------|--------|
| `name` | string | Поиск по названию (частичное совпадение, регистрозависимо) | `?name=цифровая` |
| `program_type` | string | Точное совпадение типа программы | `?program_type=PROF` |
| `study_form` | string | Точное совпадение формы обучения | `?study_form=FT` |
| `DOT` | boolean (true/false) | Фильтр по наличию электронного обучения | `?DOT=true` |

## Примеры запросов

### cURL

```bash
curl -X GET "https://bitrix24.tuna-edu.ru/api/program/?name=менеджмент&program_type=PROF&DOT=true" \
  -H "Authorization: Token ваш_токен"
```

### JavaScript (fetch)

```javascript
fetch('/api/program/?name=менеджмент&study_form=FT', {
    headers: { 'Authorization': 'Token ваш_токен' }
})
.then(res => res.json())
.then(data => console.log(data));
```

### Python (requests)

```python
import requests
params = {'program_type': 'PROF', 'DOT': 'false'}
headers = {'Authorization': 'Token ваш_токен'}
response = requests.get('https://bitrix24.tuna-edu.ru/api/program/', params=params, headers=headers)
print(response.json())
```

## Пример успешного ответа (HTTP 200)

```json
[
    {
      "id": 6,
      "name": "Оператор БПЛА 30 КГ",
      "academic_hours": 20,
      "program_type": "PROF",
      "study_form": "FT",
      "DOT": false,
      "description": "",
      "duration": 0,
      "final_attestation": 8,
      "created_at": "2026-03-11T14:10:32.638704+04:00",
      "updated_at": "2026-03-19T16:19:44.233163+04:00",
      "activities": null
    }
]
```

## Возможные ошибки

| Код | Описание | Пример ответа |
|-----|----------|----------------|
| 401 | Неверный или отсутствующий токен | `{"detail": "Authentication credentials were not provided."}` |
| 200 (с пустым списком) | Фильтры не дали результатов | `[]` |

## Примечания

- Все параметры необязательны. Можно комбинировать любые из них.
- Параметр `name` ищет по вхождению подстроки (в зависимости от БД).
- `program_type` и `study_form` чувствительны к регистру — используйте значения точно как в системе.
- Для `DOT` допустимы `true`, `false` или отсутствие параметра (все записи).
