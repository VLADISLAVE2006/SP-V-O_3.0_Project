# Бэкенд системы опросов

Python 3.13, Django 5.2 LTS, Django REST Framework, PostgreSQL 18, Channels, Redis, Daphne и Docker Compose. Фронтенд разрабатывается отдельно.

Реализованы 44 REST-операции из «Списка API» и WebSocket результатов. Модель содержит 13 предметных таблиц из «Описания БД», включая настоящий составной PK у `comment_likes`. Служебные таблицы Django создаются отдельно. В Python атрибут `User.password` соответствует SQL-колонке `password_hash`; хеширование выполняет Django.

## Запуск в Docker

Откройте терминал в папке `backend`. На компьютере должен работать Docker Desktop с Linux-контейнерами.

1. Скопируйте `.env.example` в `.env`, если файла ещё нет. Задайте собственные `DJANGO_SECRET_KEY` и пароль PostgreSQL; пароль в `DATABASE_URL` должен совпадать с `POSTGRES_PASSWORD`. Во время первоначальной настройки локальный `.env` уже создан с отдельными случайными значениями.
2. Выполните:

```powershell
docker compose -p codex-polls-er4 up -d --build
```

Адрес API: `http://localhost:18083/api`. Swagger: `http://localhost:18083/api/docs`. OpenAPI: `http://localhost:18083/api/schema`. Проверка соединения с БД: `http://localhost:18083/api/health`.

Сервисы `db` и `redis` не публикуют порты на компьютере. API слушает только `127.0.0.1:18083`. `migrate` применяет миграции и создаёт роли `user`, `moderator`, `admin`, затем запускаются `backend` и `scheduler`. Планировщик раз в секунду публикует отложенные опросы, завершает просроченные и удаляет истёкшие сессии.

Создание администратора без публичной регистрации с повышенной ролью:

```powershell
docker compose -p codex-polls-er4 exec backend python manage.py createsuperuser
```

Введите почту, никнейм и пароль. Управление пользователями выполняется через `/api/admin/...`; встроенная HTML-админка Django не подключена.

Остановка с сохранением данных:

```powershell
docker compose -p codex-polls-er4 down
```

Не добавляйте `-v`, если хотите сохранить базу и аватары. После изменения Python-кода повторите запуск с `--build`: исходники упакованы в образ, а не подключены как изменяемый том.

## Подготовка для фронтенда и тестирования

```powershell
docker compose -p codex-polls-er4 exec backend python manage.py seed_demo
```

Команда создаёт пять демонстрационных аккаунтов и шесть опросов разных состояний только при `DJANGO_DEBUG=1`. Существующие пароли и состояния не сбрасывает. Логины, пароль и сценарии приведены в [инструкции тестировщику](TESTING.md).

- [FRONTEND.md](FRONTEND.md) — HTTP, cookie, токены, WebSocket и форматы ответов.
- [TESTING.md](TESTING.md) — демо-данные, ручные сценарии и регрессионные проверки.
- [DEVELOPMENT.md](DEVELOPMENT.md) — где менять код, как создать миграцию и обновить OpenAPI.
- [Коллекция Postman](postman/polls.postman_collection.json) — последовательный сценарий с автоматической подстановкой токенов и идентификаторов.

## Проверки

Все проверки одной командой в PowerShell: `./scripts/check.ps1`. Скрипт должен завершиться сообщением `All checks passed.`.

Полный набор, включая параллельные голоса и ротацию токенов на PostgreSQL:

```powershell
docker compose -p codex-polls-er4 exec backend python manage.py test --verbosity 2
docker compose -p codex-polls-er4 exec backend python manage.py check
docker compose -p codex-polls-er4 exec backend python manage.py makemigrations --check --dry-run
docker compose -p codex-polls-er4 exec backend python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yaml
docker compose -p codex-polls-er4 exec backend python -m ruff check .
```

Тесты создают отдельную базу `test_polls` и удаляют её после завершения. Рабочую базу не очищают. У пользователя БД должны быть права на создание тестовой базы; локальный пользователь контейнера PostgreSQL их имеет.

Быстрая локальная проверка без Docker в PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
$env:DJANGO_SECRET_KEY = 'local-tests-only-change-before-deployment-12345'
$env:USE_SQLITE = '1'
$env:DJANGO_DEBUG = '1'
$env:COOKIE_SECURE = '0'
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py test
.venv/Scripts/python.exe manage.py runserver 127.0.0.1:18083
```

SQLite — только вспомогательный режим: два теста блокировок строк в нём пропускаются. Для обновлений между отдельными процессами нужен Redis. Без `REDIS_URL` используется канал в памяти одного процесса. Для публикации и завершения без HTTP-запросов запустите в отдельном терминале с теми же переменными `python manage.py poll_scheduler`.

## Структура

- `config/` — настройки, HTTP и ASGI-маршруты.
- `core/models.py`, `core/migrations/` — предметная модель, ограничения БД и миграции.
- `core/auth.py` — JWT, хеши refresh-токенов, отзыв и ротация сессий.
- `core/serializers.py` — входные данные и схемы ответов.
- `core/services.py` — голосование, результаты, переходы статусов и предупреждения.
- `core/views.py` — REST-методы и проверки прав.
- `core/consumers.py` — WebSocket с повторной проверкой доступа.
- `core/exports.py` — CSV, XLSX и PDF.
- `core/tests/` — API, ограничения, WebSocket и параллельные запросы.
- `FRONTEND.md` — соглашения и примеры для разработчика фронтенда.

## Принятые уточнения контракта

В исходных документах не все форматы ответов и пограничные случаи расписаны. Для реализации приняты следующие решения:

- Пути REST без завершающего `/`; WebSocket — с `/`.
- Списки возвращают `items`, `total`, `has_more`; `limit` от 1 до 100, по умолчанию 20.
- Комментарии возвращаются плоским списком вместе с ответами. Поле `parent_id` задаёт дерево; один список пагинируется целиком.
- Проценты вариантов считаются от числа прохождений опроса; при множественном выборе сумма процентов может превышать 100.
- Результаты завершённого опроса, как и активного, доступны автору и участникам. Это следует из доступа «Участник, автор» в списке API; для общедоступных итогов потребуется отдельно изменить правило.
- У `scale` сервер создаёт варианты `1`–`5`. Черновик создаётся с минимум одним валидным вопросом.
- После смены пароля возвращается новая пара токенов, все прежние сессии завершаются. Ротация refresh также отзывает старый access соответствующей сессии: access проверяется по существующей сессии.
- Метка гостя — подписанный UUID в HttpOnly-cookie. Удаление cookie позволяет гостю представиться новым участником: это ограничение указанной в проекте защиты по браузеру.
- При модерационном удалении комментария поддержаны те же `is_violation` и `comment`, что при удалении опроса.
- API не понижает роль администратора и не позволяет администратору заблокировать себя.
- WebSocket передаёт JWT через подпротокол, а не через URL. При отзыве доступа соединение закрывается перед следующим событием или в течение 10 секунд.

## Перед размещением на сервере

Текущий Compose предназначен для локальной разработки. Для внешнего сервера задайте `DJANGO_DEBUG=0`, собственные секреты, точные домены в `DJANGO_ALLOWED_HOSTS` и `CORS_ALLOWED_ORIGINS`, `COOKIE_SECURE=1`, настройте HTTPS, раздачу `/media/` и `/static/` через обратный прокси и резервное копирование PostgreSQL. Если фронтенд и API находятся на разных сайтах, cookie гостя требует `COOKIE_SAMESITE=None` и HTTPS; предпочтителен один сайт или общий домен. Для production также нужен общий кеш ограничений частоты запросов вместо кеша в памяти процесса.

Зависимости зафиксированы в `requirements.lock`; `requirements.txt` задаёт допустимые ветки для будущего обновления. Файлы `.env`, базы, аватары и виртуальная среда исключены из Git и Docker-контекста. При работе над проектом коммиты и отправка на GitHub не выполнялись.
