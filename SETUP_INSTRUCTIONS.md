# 🛠️ Инструкции по установке и настройке

## 🖥️ Локальная разработка

### Предварительные требования

- Python 3.9 или выше
- PostgreSQL 12 или выше (или Docker)
- Git

### Пошаговая установка

#### 1. Клонирование репозитория
```bash
git clone https://github.com/your-username/russian-telegram-ai-bot.git
cd russian-telegram-ai-bot
```

#### 2. Создание виртуального окружения
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

#### 3. Установка зависимостей
```bash
pip install -r requirements.txt
```

#### 4. Настройка переменных окружения
```bash
# Скопируйте пример конфига
cp .env.example .env

# Отредактируйте .env файл с вашими данными
nano .env  # или используйте любой редактор
```

#### 5. Настройка базы данных

**Вариант A: Использование Docker (рекомендуется)**
```bash
# Запуск PostgreSQL в контейнере
docker-compose up postgres -d

# DATABASE_URL в .env должен быть:
# DATABASE_URL=postgresql://postgres:password@localhost:5432/russian_bot_db
```

**Вариант B: Локальная установка PostgreSQL**
```bash
# Создание базы данных
createdb russian_bot_db

# DATABASE_URL в .env:
# DATABASE_URL=postgresql://username:password@localhost:5432/russian_bot_db
```

#### 6. Запуск приложения
```bash
# Развертывание (создание таблиц происходит автоматически)
python -m app.main

# Или с перезагрузкой при изменениях
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 7. Проверка работы
- Откройте http://localhost:8000/health
- Должен вернуться статус "healthy"

## 🐳 Запуск с Docker

### Полный стек с Docker Compose
```bash
# Создайте .env файл с вашими токенами
cp .env.example .env
# Отредактируйте .env

# Запуск всех сервисов
docker-compose up --build

# В фоновом режиме
docker-compose up -d --build
```

### Только приложение в Docker
```bash
# Сборка образа
docker build -t russian-telegram-bot .

# Запуск (при наличии внешней БД)
docker run --env-file .env -p 8000:8000 russian-telegram-bot
```

## ☁️ Продакшн деплой

### Railway (рекомендуется)

1. **Форк репозитория** на GitHub
2. **Создайте проект на Railway**:
   - Подключите GitHub репозиторий
   - Добавьте PostgreSQL Add-on
3. **Настройте переменные окружения** (см. .env.example)
4. **Деплой происходит автоматически**

### Другие платформы

**Heroku:**
```bash
# Создание приложения
heroku create your-bot-name

# Добавление PostgreSQL
heroku addons:create heroku-postgresql:hobby-dev

# Настройка переменных
heroku config:set TELEGRAM_BOT_TOKEN=your_token
heroku config:set OPENAI_API_KEY=your_key
# ... другие переменные

# Деплой
git push heroku main
```

**DigitalOcean App Platform:**
1. Создайте App из GitHub репозитория
2. Добавьте Managed Database (PostgreSQL)
3. Настройте environment variables
4. Деплой произойдет автоматически

**VPS (Ubuntu/Debian):**
```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка зависимостей
sudo apt install python3 python3-pip python3-venv postgresql nginx

# Клонирование и настройка
git clone https://github.com/your-username/russian-telegram-ai-bot.git
cd russian-telegram-ai-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Настройка PostgreSQL
sudo -u postgres createuser botuser
sudo -u postgres createdb russian_bot_db
sudo -u postgres psql -c "ALTER USER botuser PASSWORD 'your_password';"

# Настройка systemd сервиса
sudo cp deployment/bot.service /etc/systemd/system/
sudo systemctl enable bot
sudo systemctl start bot

# Настройка Nginx (опционально)
sudo cp deployment/nginx.conf /etc/nginx/sites-available/bot
sudo ln -s /etc/nginx/sites-available/bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 🔧 Разработка

### Структура проекта
```
app/
├── main.py              # Точка входа FastAPI
├── config.py           # Конфигурация
├── bot.py              # Инициализация бота
├── db.py               # База данных
├── handlers/           # Обработчики сообщений
├── services/           # Бизнес-логика
└── utils/              # Утилиты
```

### Добавление новой функции

1. **Создайте handler**:
```python
# app/handlers/my_feature.py
from aiogram import Router

router = Router(name="my_feature")

@router.message(...)
async def my_handler(message):
    # Ваша логика
    pass
```

2. **Зарегистрируйте router**:
```python
# app/bot.py
from app.handlers.my_feature import router as my_router
_dispatcher.include_router(my_router)
```

### Тестирование

```bash
# Запуск тестов
pytest

# Покрытие кода
pytest --cov=app

# Конкретный тест
pytest tests/test_handlers.py::test_start_command
```

### Линтинг и форматирование

```bash
# Форматирование кода
black app/
isort app/

# Проверка стиля
flake8 app/

# Проверка типов
mypy app/
```

## 🐛 Отладка

### Общие проблемы

**Бот не отвечает:**
1. Проверьте правильность TELEGRAM_BOT_TOKEN
2. Убедитесь, что webhook URL доступен
3. Проверьте логи приложения

**Ошибки OpenAI:**
1. Проверьте OPENAI_API_KEY
2. Убедитесь в наличии кредитов на счете
3. Проверьте лимиты API

**Ошибки БД:**
1. Проверьте DATABASE_URL
2. Убедитесь, что PostgreSQL запущен
3. Проверьте права доступа к БД

### Логирование

```python
import logging

# Включение отладочных логов
logging.basicConfig(level=logging.DEBUG)

# Логи отдельных модулей
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiogram").setLevel(logging.INFO)
```

### Мониторинг

- **Health check**: `GET /health`
- **Логи**: Проверяйте console output или файлы логов
- **Метрики**: Встроенная аналитика через `/stats` (для админов)

## 📦 Обновление

### Обновление зависимостей
```bash
# Обновление всех пакетов
pip install --upgrade -r requirements.txt

# Обновление конкретного пакета
pip install --upgrade openai

# Сохранение новых версий
pip freeze > requirements.txt
```

### Миграции БД
Схема БД обновляется автоматически при запуске приложения. Новые таблицы и индексы создаются через `MIGRATIONS_SQL` в `db.py`.

### Backup и восстановление
```bash
# Создание backup
pg_dump $DATABASE_URL > backup.sql

# Восстановление
psql $DATABASE_URL < backup.sql
```

---

**Успешного развертывания! 🚀**