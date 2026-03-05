# Человек 2035 — AI Telegram Platform

Полностью автоматизированная Telegram-платформа с AI-ботом на тему **"Человек 2035 — уже сегодня"**.

## Что умеет бот

- 🔮 **AI-ответы** на вопросы о будущем (Claude API)
- 💡 **Инсайт дня** — ежедневная автогенерация контента
- 🗺 **Личный план до 2035** (для Pro/Expert)
- 📊 **Персонализация** по 4 направлениям: технологии, здоровье, финансы, психология
- ⭐️ **Монетизация**: Free (3 запроса/день) / Pro / Expert подписки
- 📡 **Автопостинг** в Telegram канал (07:00 и 17:00)

## Быстрый старт

### 1. Настройка

```bash
cp .env.example .env
# Заполни .env своими ключами
```

### 2. Запуск локально

```bash
pip install -r requirements.txt
python main.py
```

### 3. Запуск через Docker

```bash
cd docker
docker-compose up -d
```

## Переменные окружения

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Telegram Bot Token от @BotFather |
| `ANTHROPIC_API_KEY` | Claude API ключ (console.anthropic.com) |
| `CHANNEL_ID` | ID/username Telegram канала (например @human2035) |
| `ADMIN_IDS` | Telegram ID администраторов через запятую |
| `DATABASE_URL` | URL базы данных (по умолчанию SQLite) |

## Команды администратора

| Команда | Описание |
|---|---|
| `/stats` | Статистика пользователей и доход |
| `/post <тема>` | Создать и опубликовать пост в канал |
| `/insight` | Срочно опубликовать инсайт |
| `/setpro <user_id>` | Выдать Pro подписку пользователю |

## Архитектура

```
main.py                    # Точка входа
├── bot/
│   ├── handlers/
│   │   ├── start.py      # Онбординг, профиль, подписки
│   │   ├── ai_chat.py    # AI-диалог, инсайты, роадмап
│   │   └── admin.py      # Админ-команды
│   └── services/
│       ├── claude_ai.py  # Интеграция с Claude API
│       ├── database.py   # SQLAlchemy модели и запросы
│       └── scheduler.py  # Автопостинг в канал
├── config/
│   └── settings.py       # Конфигурация из .env
└── docker/
    ├── Dockerfile
    └── docker-compose.yml
```

## Монетизация

- **Free**: 3 AI-запроса/день
- **Pro** (490₽/мес): безлимит + личный план до 2035
- **Expert** (1990₽/мес): всё из Pro + AI-коучинг + мастермайнд
