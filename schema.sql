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