# Документация REST API Contacts

Текст соответствует странице гида `/api/guide/?contact`. Базовый URL в примерах: `https://bitrix24.tuna-edu.ru`.

## Содержание

- [Введение](#введение)
- [1. Аутентификация](#1-аутентификация)
- [2. Основной эндпоинт](#2-основной-эндпоинт)
- [3. Типы контактов](#3-типы-контактов)
- [4. Фильтрация результатов](#4-фильтрация-результатов)
- [5. Добавление и изменение](#5-добавление-и-изменение)
- [6. Формат ответа](#6-формат-ответа)
- [7. Коды ответов и ошибки](#7-коды-ответов-и-ошибки)

## Введение

Добро пожаловать в документацию REST API для работы с контактами организаций. Этот API предоставляет доступ к контактным лицам и отделам, связанным с организациями.

**Особенности API:** поддерживает 4 типа контактов: физические лица, отделы, основной и другое. Для физлиц и отделов возвращаются свои наборы полей.

## 1. Аутентификация

Для доступа к API требуется токен.

1. В админ-панели Django перейдите в раздел «Токены».
2. Создайте новый токен для нужного пользователя.
3. Сохраните токен для будущего использования.

## 2. Основной эндпоинт

### 2.1 Получение данных о контактах

| | |
|---|---|
| **Эндпоинт** | `/api/contact/` |
| **Метод HTTP** | GET |
| **Аутентификация** | Требуется (токен в заголовке Authorization) |
| **Пагинация** | Поддерживается (стандартная Django REST) |

### 2.2 Формат запроса

**Заголовки обязательные:**

| Заголовок | Значение | Описание |
|-----------|----------|----------|
| `Authorization` | `Token YOUR_TOKEN` | Токен аутентификации |
| `Accept` | `application/json` | Формат ответа (рекомендуется) |

### 2.3 Примеры использования

**Пример 1: JavaScript (Fetch API)**

```javascript
// Получение всех контактов
fetch('https://bitrix24.tuna-edu.ru/api/contact/', {
    method: 'GET',
    headers: {
        'Authorization': 'Token 4a8389aa7f015d3a68e44e3f4bae94d63c7ac097',
        'Accept': 'application/json'
    }
})
.then(response => response.json())
.then(data => console.log(data))
.catch(error => console.error('Ошибка:', error));
```

**Пример 2: cURL**

```bash
curl -X GET 'https://bitrix24.tuna-edu.ru/api/contact/' \
  -H 'Authorization: Token 4a8389aa7f015d3a68e44e3f4bae94d63c7ac097' \
  -H 'Accept: application/json'
```

**Пример 3: Python (Requests)**

```python
import requests
headers = {
    'Authorization': 'Token 4a8389aa7f015d3a68e44e3f4bae94d63c7ac097',
    'Accept': 'application/json'
}
response = requests.get('https://bitrix24.tuna-edu.ru/api/contact/', headers=headers)
data = response.json()
print(data)
```

## 3. Типы контактов

Набор полей в ответе зависит от типа контакта.

### 3.1 Тип `person` (физическое лицо)

Сотрудник организации. Возвращаемые поля:

- `type` — тип контакта (`"person"`)
- `comment` — комментарий
- `current` — актуальность контакта
- `organization` — ИНН организации
- `first_name`, `last_name`, `middle_name`
- `position` — должность
- `first_name_dat`, `last_name_dat`, `middle_name_dat`, `position_dat` — дательный падеж
- `manager` — является ли руководителем

### 3.2 Тип `department` (отдел)

- `type` — `"department"`
- `comment`, `current`, `organization` (ИНН)
- `department_name` — название отдела

### 3.3 Тип `main` (основной)

- `type` — `"main"`
- `comment`, `current`, `organization` (ИНН)

### 3.4 Тип `other` (другое)

- `type` — `"other"`
- `comment`, `current`, `organization` (ИНН)

**Примечание:** для корректной фильтрации используйте фильтры, соответствующие типу контакта.

## 4. Фильтрация результатов

API поддерживает фильтрацию контактов по различным параметрам.

### 4.1 Доступные фильтры

| Фильтр | Параметр | Описание | Тип поиска | Примечание |
|--------|----------|----------|------------|------------|
| Организация | `organization` | ИНН организации | Точное совпадение, множественное | — |
| Тип контакта | `type` | person / department / main / other | Точное совпадение, множественное | — |
| Подразделение | `department` | Название отдела (частичное совпадение) | Множественное (icontains) | Только для отделов |
| Руководитель | `manager` | Фильтр по руководителям | Булевый | Только для сотрудников |
| Актуальность | `current` | Актуальные контакты | Булевый | true/false |

### 4.2 Синтаксис фильтрации

```
/api/contact/?filter1=value1&filter2=value2
```

**Множественные значения:** `?type=person&type=department` или `?department=IT,Кадры`

### 4.3 Примеры фильтрации

**Пример 1: контакты нескольких организаций**

```
https://bitrix24.tuna-edu.ru/api/contact/?organization=546123&organization=713191
```

**Пример 2: физические лица + руководители**

```
https://bitrix24.tuna-edu.ru/api/contact/?type=person&manager=true
```

**Пример 3: несколько отделов в организации**

```
https://bitrix24.tuna-edu.ru/api/contact/?type=department&organization=313313&department=цифровизация&department=кадры
```

**Пример 4: комбинированная фильтрация**

```
https://bitrix24.tuna-edu.ru/api/contact/?type=department&type=person&organization=313313&department=отдел,it
```

**Поддержка множественной фильтрации:**

- `?organization=123&organization=456` или `organization=123,456`
- `department` — частичное совпадение (icontains)
- `manager=true` только при `type=person`
- `department` в смысле фильтра — только при `type=department`

## 5. Добавление и изменение

API поддерживает создание и изменение контактов организации.

| Действие | Метод | Эндпоинт | Обязательные поля |
|----------|-------|----------|-------------------|
| Добавление | `POST` | `/api/contact/add/` | `organization`, `type` |
| Изменение | `PATCH` | `/api/contact/update/` | `id` |

**Пример создания контакта:**

```json
{
  "organization": "7701234567",
  "type": "person",
  "first_name": "Иван",
  "last_name": "Иванов",
  "position": "Руководитель",
  "manager": true,
  "current": true
}
```

**Пример изменения контакта:**

```json
{
  "id": 1,
  "position": "Директор департамента",
  "current": true
}
```

## 6. Формат ответа

### 6.1 Успешный ответ (HTTP 200 OK)

API возвращает список контактов. Структура зависит от типа.

```json
[
  {
    "type": "person",
    "comment": "Основной контакт по проекту",
    "current": true,
    "organization": "313313",
    "first_name": "Иван",
    "last_name": "Иванов",
    "middle_name": "Иванович",
    "position": "Начальник отдела",
    "first_name_dat": "Ивану",
    "last_name_dat": "Иванову",
    "middle_name_dat": "Ивановичу",
    "position_dat": "Начальнику отдела",
    "manager": true
  },
  {
    "type": "department",
    "comment": "Отдел цифровизации",
    "current": true,
    "organization": "313313",
    "department_name": "Отдел цифровой трансформации"
  },
  {
    "type": "person",
    "comment": "Бывший сотрудник",
    "current": false,
    "organization": "552233",
    "first_name": "Петр",
    "last_name": "Петров",
    "middle_name": "Петрович",
    "position": "Бывший директор",
    "first_name_dat": "Петру",
    "last_name_dat": "Петрову",
    "middle_name_dat": "Петровичу",
    "position_dat": "Бывшему директору",
    "manager": false
  }
]
```

### 6.2 Структура данных для типа `person`

| Поле | Тип | Описание |
|------|-----|----------|
| `type` | String | Всегда `"person"` |
| `comment` | String | Комментарий |
| `current` | Boolean | Актуальность контакта |
| `organization` | String | ИНН организации |
| `first_name` | String | Имя |
| `last_name` | String | Фамилия |
| `middle_name` | String | Отчество |
| `position` | String | Должность |
| `first_name_dat` | String | Имя в дательном падеже |
| `last_name_dat` | String | Фамилия в дательном падеже |
| `middle_name_dat` | String | Отчество в дательном падеже |
| `position_dat` | String | Должность в дательном падеже |
| `manager` | Boolean | Является ли руководителем |

### 6.3 Структура данных для типа `department`

| Поле | Тип | Описание |
|------|-----|----------|
| `type` | String | Всегда `"department"` |
| `comment` | String | Комментарий |
| `current` | Boolean | Актуальность контакта |
| `organization` | String | ИНН организации |
| `department_name` | String | Название отдела |

## 7. Коды ответов и ошибки

### 7.1 Успешные коды

| Код | Описание |
|-----|----------|
| `200` | OK — запрос выполнен успешно |

### 7.2 Коды ошибок

| Код | Описание | Решение |
|-----|----------|---------|
| `400` | Bad Request | Проверьте синтаксис URL и параметры фильтрации |
| `401` | Unauthorized | Убедитесь, что передали корректный токен |
| `403` | Forbidden | Токен не имеет прав на доступ к API |
| `404` | Not Found | Проверьте URL эндпоинта |
| `500` | Internal Server Error | Попробуйте позже или обратитесь к администратору |

### 7.3 Примеры ошибок

**Ошибка 401: отсутствует токен**

```json
{
    "detail": "Authentication credentials were not provided."
}
```

**Решение:** добавьте заголовок `Authorization` с вашим токеном.
