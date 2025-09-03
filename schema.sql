-- Таблица конфигурации бота
CREATE TABLE IF NOT EXISTS bot_config (
    id SERIAL PRIMARY KEY,                    -- Уникальный идентификатор записи
    prompt TEXT NOT NULL,                     -- Системный промпт для ИИ
    menu JSONB NOT NULL DEFAULT '{}'::jsonb,  -- Конфигурация меню в формате JSON
    updated_at TIMESTAMP DEFAULT now()        -- Время последнего обновления
);

-- Таблица логов взаимодействий
CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,                    -- Уникальный идентификатор записи
    username TEXT,                            -- Имя пользователя Telegram
    command TEXT,                             -- Команда, которую использовал пользователь
    args TEXT,                                -- Аргументы команды/текст сообщения
    answer TEXT,                              -- Ответ бота
    created_at TIMESTAMP DEFAULT now()        -- Время создания записи
);

-- Таблица статуса бота
CREATE TABLE IF NOT EXISTS bot_status (
    id SERIAL PRIMARY KEY,
    is_active BOOLEAN DEFAULT TRUE
);

-- Таблица пользовательских настроек
CREATE TABLE IF NOT EXISTS user_settings (
    id SERIAL PRIMARY KEY,                    -- Уникальный идентификатор записи
    user_id BIGINT UNIQUE NOT NULL,           -- ID пользователя Telegram
    preferred_model TEXT NOT NULL DEFAULT 'gpt-4o', -- Предпочтительная модель OpenAI
    tts_enabled BOOLEAN NOT NULL DEFAULT FALSE, -- Включены ли голосовые ответы
    tts_voice TEXT NOT NULL DEFAULT 'alloy',  -- Голос для синтеза речи
    personal_assistant_enabled BOOLEAN NOT NULL DEFAULT FALSE, -- Включен ли персональный ассистент
    created_at TIMESTAMP DEFAULT now(),       -- Время создания записи
    updated_at TIMESTAMP DEFAULT now()        -- Время последнего обновления
);

-- Таблица истории диалогов
CREATE TABLE IF NOT EXISTS dialog_history (
    id SERIAL PRIMARY KEY,                    -- Уникальный идентификатор записи
    user_id BIGINT NOT NULL,                  -- ID пользователя Telegram
    role TEXT NOT NULL,                       -- Роль (user или assistant)
    content TEXT NOT NULL,                    -- Содержание сообщения
    created_at TIMESTAMP DEFAULT now()        -- Время создания записи
);
