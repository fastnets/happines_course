# Архитектура проекта `happines_course`

## 1) Общая идея
Проект построен как Telegram-бот на `python-telegram-bot` с явным разделением на:
- `handlers` (входные точки Telegram),
- `services` (бизнес-логика),
- `repositories` (работа с БД),
- `scheduling` (планирование и доставка отложенных сообщений через outbox).

Главная цель архитектуры: предсказуемая доставка контента/напоминаний и идемпотентные начисления баллов.

## 2) Точка входа и сборка зависимостей
`main.py`:
- читает настройки (`entity/settings.py`),
- поднимает БД и схему (`entity/db.py`),
- создает все сервисы в словаре `services`,
- регистрирует обработчики (admin -> user -> questionnaire -> learning),
- запускает periodic tick раз в 3 секунды (`scheduling/worker.py:tick`),
- запускает генерацию daily pack (по UTC-полуночи и один раз на старте).

Именно `services` является контейнером зависимостей, который передается в handlers.

## 3) Слои и ответственность
### 3.1 Handlers (интеграционный слой)
- `user/user_handlers.py`: пользовательские меню, регистрация, день/прогресс/напоминания/привычки/поддержка.
- `learning/learning_handlers.py`: callback-и по обучению и заданиям.
- `questionnaires/questionnaire_handlers.py`: анкеты и ответы.
- `admin/admin_handlers.py`: админское управление контентом, аналитикой и тикетами.

Handlers:
- читают update/context,
- вызывают сервисы,
- отрисовывают тексты/кнопки (`ui/texts.py`, `ui/keyboards/*`),
- почти не содержат бизнес-правил.

### 3.2 Services (бизнес-логика)
- `user/user_service.py`: профиль/пользовательские операции.
- `learning/learning_service.py`: просмотр лекций, ответы на задания, прогресс, баллы.
- `questionnaires/questionnaire_service.py`: CRUD/получение анкет.
- `admin/admin_service.py`: операции админ-панели.
- `analytics/analytics_service.py`: пользовательская аналитика и прогресс.
- `analytics/admin_analytics_service.py`: сводная аналитика для админа.
- `core/achievement_service.py`: правила и выдача ачивок.
- `core/habit_service.py`: привычки и отметка done/skip.
- `core/personal_reminder_service.py`: CRUD персональных одноразовых напоминаний.
- `core/support_service.py`: тикеты поддержки user -> admin -> user.
- `core/daily_pack_service.py`: генерация дневного AI-пака (цитата/совет/фильм/книга и т.д.).
- `core/ai_feedback_service.py`: интеграция AI-ответов/фидбэка.

### 3.3 Repositories (доступ к данным)
`entity/repositories/*`:
- инкапсулируют SQL и структуру таблиц,
- возвращают словари (`dict_row`),
- используются только из сервисов/планировщиков (не из UI напрямую).

## 4) Планировщик и доставка (ключевая часть)
### 4.1 Механика
Раз в 3 секунды `tick` делает:
1. `schedule.schedule_due_jobs()` — планирование контента дня + daily reminder.
2. `habit_schedule.schedule_due_jobs()` — планирование привычек.
3. `personal_reminder_schedule.schedule_due_jobs()` — планирование персональных напоминаний.
4. `_process_outbox(...)` — отправка due `pending` jobs из `outbox_jobs`.

### 4.2 Outbox-паттерн
Таблица `outbox_jobs` хранит отложенные задачи с `run_at`, `payload_json`, `status`.
Worker выбирает due jobs, пытается отправить, затем:
- `mark_sent` при успехе,
- `mark_failed` при ошибке.

### 4.3 Идемпотентность
Используются несколько уровней защиты:
- `job_key` в payload и проверка `exists_job_for(...)` перед созданием,
- `sent_jobs` (PK на `user_id + content_type + day_index + for_date`) для защиты от повторной доставки,
- `points_ledger` + `source_key` для недопущения повторных начислений,
- `habit_occurrences` c `UNIQUE(habit_id, scheduled_at)` для привычек.

## 5) Доменная карта данных (БД)
Основные таблицы:
- Пользователи и состояние: `users`, `user_state`, `admins`, `enrollments`.
- Обучение: `lessons`, `quests`, `progress`, `quest_answers`, `deliveries`, `sent_jobs`.
- Начисления и достижения: `points_ledger`, `user_achievements`.
- Анкеты: `questionnaires`, `questionnaire_responses`.
- Планировщик: `outbox_jobs`.
- Привычки: `habits`, `habit_occurrences`.
- Персональные напоминания: `personal_reminders`.
- Поддержка: `support_tickets`.
- Daily AI pack: `daily_sets`, `daily_items`.

Схема и миграции живут в `entity/db.py` (`SCHEMA_SQL`, `MIGRATIONS_SQL`).

## 6) Потоки по ключевым фичам
### 6.1 "Мой день"
Планировщик создает `day_lesson`/`day_quest` job -> worker отправляет -> пользователь отмечает просмотр/отвечает -> сервис обновляет `progress`/`quest_answers`/`points_ledger`.

### 6.2 Напоминания
- Daily reminder: вычисляется после delivery-time c учетом quiet hours.
- Habit reminder: по occurrence, с кнопками `✅ Выполнено` / `➖ Пропустить`.
- Personal reminder: одноразовый `start_at`, после отправки повтор не планируется.

### 6.3 Поддержка (тикеты)
Пользователь формирует запрос -> создается `support_tickets` (`open`) -> админ отвечает/закрывает -> ответ возвращается пользователю.

## 7) UI слой
Тексты и кнопки вынесены отдельно:
- `ui/texts.py`,
- `ui/keyboards/menus.py`,
- `ui/keyboards/reply.py`.

Это упрощает поддержку UX без изменения бизнес-логики.

## 8) Тестовый контур
Тесты в `tests/` покрывают критичные пути:
- расписание и outbox,
- admin handlers,
- learning/habit behavior,
- personal reminders scheduling,
- support service,
- user progress + achievements,
- admin analytics.

CI запускает `unittest` через GitHub Actions (`.github/workflows/tests.yml`).

## 9) Куда расширять дальше
Без перелома архитектуры можно безопасно добавлять:
- новые типы outbox-jobs (новые `kind` в worker),
- новые разделы админ-аналитики через `admin_analytics_repo/service`,
- новые правила ачивок в `core/achievement_service.py`,
- более глубокие продуктовые отчеты на базе `points_ledger`, `progress`, `questionnaire_responses`.
