"""
Основной модуль Telegram‑бота с поддержкой команды /suggest_prompt и логированием.

Этот модуль использует библиотеку aiogram v3 для асинхронной работы с
Telegram‑API, а также асинхронный драйвер asyncpg для записи логов в
PostgreSQL. Он подключается к OpenAI через модуль ai для генерации
ответов на сообщения пользователей.
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

from .config import settings
from .suggest import generate_prompt_from_logs
from .ai import openai_chat, openai_image
from .admin import is_admin, cmd_admin_stats, cmd_errors, cmd_bot_on, cmd_bot_off, is_bot_active

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Пул подключений к базе данных (инициализируется при запуске)
pool: asyncpg.pool.Pool | None = None

# Улучшенный системный промпт по умолчанию для диалогов
DEFAULT_SYSTEM_PROMPT = (
    "Ты — интеллектуальный Telegram-бот. Твои задачи:\n"
    "- Отвечать максимально понятно и дружелюбно на русском языке.\n"
    "- Поддерживать контекст беседы (используй историю сообщений из базы).\n"
    "- Если пользователь просит нарисовать или сгенерировать картинку — используй OpenAI Images.\n"
    "- Если спрашивают про статистику или историю — достань данные из PostgreSQL.\n"
    "- Модель: " + settings.OPENAI_MODEL + ".\n"
    "- Общайся живо, иногда добавляй смайлы 🙂."
)

# Текст приветствия
WELCOME_TEXT = """
Добро пожаловать, {username}!
Сегодня {date}, ваш лимит: 20 запросов

🧠 Ваш AI Agent

🤖 Мультимодельный AI (GPT-4o)
• 🎨 Генерация изображений  
• 📊 Продвинутая аналитика
• 💎 Персонализация

💫 Новые возможности:
• Выбор модели ИИ (/mode)
• Контекст диалога с историей
• Автоматическое распознавание запросов на изображения

🎯 Команды:
/help - Подробная помощь
/stats - Ваша статистика
/suggest_prompt - Улучшенный промпт
/art - Создать изображение
/mode - Выбрать модель ИИ
/reset_context - Сбросить контекст

Просто напишите любой вопрос и испытайте мощь современного AI!
"""

# Создание главного меню с кнопками (без админ-панели по умолчанию)
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
    [InlineKeyboardButton(text="🎨 Создать арт", callback_data="art")],
    [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    [InlineKeyboardButton(text="🧠 Умный чат", callback_data="chat")],
])

# Создание расширенного меню с админ-панелью для администраторов
admin_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
    [InlineKeyboardButton(text="🎨 Создать арт", callback_data="art")],
    [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    [InlineKeyboardButton(text="🧠 Умный чат", callback_data="chat")],
    [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")],
])


async def on_startup() -> None:
    """Функция, вызываемая при запуске бота."""
    global pool
    try:
        pool = await asyncpg.create_pool(settings.DATABASE_URL)
        logger.info("Подключение к базе данных установлено")
        
        # Применение схемы базы данных
        async with pool.acquire() as conn:
            try:
                # Проверяем существование таблиц
                tables_exist = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name IN ('logs', 'bot_config', 'bot_status')
                    )
                """)
                
                # Читаем и выполняем schema.sql
                with open("schema.sql", "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                    # Разделяем SQL команды по точке с запятой
                    commands = schema_sql.split(";")
                    for command in commands:
                        command = command.strip()
                        if command:
                            try:
                                await conn.execute(command)
                            except Exception as e:
                                logger.warning(f"Не удалось выполнить команду: {command[:50]}... Ошибка: {e}")
                
                if not tables_exist:
                    logger.info("Схема базы данных успешно применена")
                else:
                    logger.info("Таблицы уже существуют в базе данных")
            except Exception as e:
                logger.error(f"Ошибка при проверке или создании таблиц: {e}")
                # Продолжаем работу даже если не удалось создать таблицы
                logger.warning("Продолжаем работу бота без таблиц БД")
    except Exception as e:
        pool = None
        logger.error(f"Не удалось подключиться к базе данных: {e}")
        # Продолжаем работу даже если нет подключения к БД
        logger.warning("Продолжаем работу бота без подключения к БД")


async def on_shutdown() -> None:
    """Функция, вызываемая при остановке бота."""
    global pool
    if pool:
        await pool.close()
        logger.info("Подключение к базе данных закрыто")


@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """Обработчик команды /start."""
    # Формируем персонализированное приветствие
    username = message.from_user.username or message.from_user.first_name or "Пользователь"
    current_date = datetime.now().strftime("%d.%m.%Y")
    
    welcome_text = WELCOME_TEXT.format(username=username, date=current_date)
    
    # Показываем расширенное меню для администраторов
    if is_admin(message.from_user.id):
        await message.answer(welcome_text, reply_markup=admin_menu)
    else:
        await message.answer(welcome_text, reply_markup=main_menu)


@dp.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Обработчик команды /help."""
    help_text = (
        "ℹ️ <b>Доступные команды:</b>\n"
        "/start - Главное меню\n"
        "/help - Показать справку\n"
        "/stats - Показать статистику\n"
        "/suggest_prompt - Предложить улучшенный промпт\n"
        "/art - Создать изображение по описанию\n"
        "/mode - Выбрать модель ИИ (например: /mode gpt-4o)\n"
        "/reset_context - Сбросить контекст диалога\n\n"
        "Используйте кнопки меню для быстрого доступа к функциям."
    )
    
    # Добавляем информацию об админских командах для администраторов
    if is_admin(message.from_user.id):
        help_text += (
            "\n\n👑 <b>Админ-команды:</b>\n"
            "/admin - Админ-панель\n"
            "/admin_stats - Статистика бота\n"
            "/errors - Последние ошибки\n"
            "/bot_on - Включить бота\n"
            "/bot_off - Выключить бота"
        )
    
    await message.answer(help_text)


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    """Обработчик команды /stats."""
    if not pool:
        await message.answer("⛔ База данных недоступна. Статистика временно недоступна.")
        return
    
    try:
        async with pool.acquire() as conn:
            # Получаем общее количество записей в логах
            total_logs = await conn.fetchval("SELECT COUNT(*) FROM logs")
            
            # Получаем количество уникальных пользователей
            unique_users = await conn.fetchval("SELECT COUNT(DISTINCT username) FROM logs WHERE username IS NOT NULL")
            
            # Получаем самые популярные команды
            popular_commands = await conn.fetch("""
                SELECT command, COUNT(*) as count 
                FROM logs 
                WHERE command IS NOT NULL 
                GROUP BY command 
                ORDER BY count DESC 
                LIMIT 5
            """)
            
        stats_text = f"📊 <b>Статистика бота:</b>\n\n"
        stats_text += f"Всего сообщений: {total_logs}\n"
        stats_text += f"Уникальных пользователей: {unique_users}\n\n"
        
        if popular_commands:
            stats_text += "<b>Популярные команды:</b>\n"
            for cmd in popular_commands:
                stats_text += f"{cmd['command']}: {cmd['count']} раз(а)\n"
        else:
            stats_text += "Пока нет данных для статистики."
            
        await message.answer(stats_text)
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await message.answer("❌ Произошла ошибка при получении статистики. Попробуйте позже.")


@dp.message(Command("suggest_prompt"))
async def cmd_suggest_prompt(message: types.Message) -> None:
    """Обработчик команды /suggest_prompt для генерации улучшенного промпта."""
    if not pool:
        await message.answer("❌ Нет подключения к базе данных. Функция предложения промпта временно недоступна.")
        return
    try:
        await message.answer("🔍 Анализирую последние запросы для предложения улучшенного промпта...")
        suggestion = await generate_prompt_from_logs(pool)
        await message.answer(f"💡 <b>Предложенный промпт:</b>\n\n{suggestion}")
    except Exception as e:
        logger.error(f"Ошибка в suggest_prompt: {e}")
        await message.answer("❌ Извините, не удалось сгенерировать предложение сейчас. Попробуйте позже.")


@dp.message(Command("art"))
async def cmd_art(message: types.Message) -> None:
    """Обработчик команды /art для генерации изображений."""
    # Извлекаем текст описания изображения
    text = message.text.replace("/art", "").strip()
    
    if not text:
        await message.answer("🎨 Укажите описание картинки, например:\n/art кот в очках на скейте")
        return
    
    try:
        # Генерируем изображение через OpenAI
        image_url = await openai_image(text)
        # Отправляем изображение пользователю
        await message.answer_photo(image_url, caption=f"✨ Ваш арт готов!\n\nОписание: {text}")
        
        # Записываем взаимодействие в базу
        if pool:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                        message.from_user.username,
                        "art",
                        text,
                        f"Сгенерировано изображение: {image_url}",
                    )
            except Exception as e:
                logger.error(f"Ошибка при записи в базу данных: {e}")
                # Продолжаем работу, даже если не удалось записать в БД
        else:
            logger.warning("Нет подключения к базе данных, пропускаем запись лога")
    except Exception as e:
        logger.error(f"Ошибка при генерации изображения: {e}")
        await message.answer("❌ Извините, произошла ошибка при генерации изображения.")


@dp.callback_query()
async def process_callback(callback_query: types.CallbackQuery) -> None:
    """Обработчик нажатий на кнопки меню."""
    await callback_query.answer()
    
    if callback_query.data == "chat":
        await callback_query.message.answer("💬 Выберите режим чата или просто отправьте мне сообщение!")
    elif callback_query.data == "art":
        await callback_query.message.answer("🎨 Отправьте мне описание изображения с командой /art\nНапример: /art кот в очках на скейте")
    elif callback_query.data == "stats":
        # Вызываем обработчик команды /stats
        await cmd_stats(callback_query.message)
    elif callback_query.data == "settings":
        await callback_query.message.answer("⚙️ Настройки бота (в разработке)")
    elif callback_query.data == "help":
        # Вызываем обработчик команды /help
        await cmd_help(callback_query.message)
    elif callback_query.data == "admin_panel":
        # Проверяем, является ли пользователь администратором
        if is_admin(callback_query.from_user.id):
            admin_panel_text = (
                "👑 <b>Админ-панель</b>\n\n"
                "Доступные команды:\n"
                "/admin_stats - Статистика бота\n"
                "/errors - Последние ошибки\n"
                "/bot_on - Включить бота\n"
                "/bot_off - Выключить бота\n\n"
                "Используйте эти команды для управления ботом."
            )
            await callback_query.message.answer(admin_panel_text)
        else:
            await callback_query.message.answer("⛔ У вас нет доступа к админ-панели.")


@dp.message(Command("admin_stats"))
async def cmd_admin_stats_handler(message: types.Message) -> None:
    """Обработчик команды /admin_stats."""
    await cmd_admin_stats(message, pool)


@dp.message(Command("errors"))
async def cmd_errors_handler(message: types.Message) -> None:
    """Обработчик команды /errors."""
    await cmd_errors(message, pool)


@dp.message(Command("bot_on"))
async def cmd_bot_on_handler(message: types.Message) -> None:
    """Обработчик команды /bot_on."""
    await cmd_bot_on(message, pool)


@dp.message(Command("bot_off"))
async def cmd_bot_off_handler(message: types.Message) -> None:
    """Обработчик команды /bot_off."""
    await cmd_bot_off(message, pool)


@dp.message(Command("mode"))
async def cmd_mode(message: types.Message, command: CommandObject) -> None:
    """Обработчик команды /mode для изменения модели AI."""
    global pool
    
    if not command.args:
        # Показываем текущую модель пользователя
        current_model = settings.OPENAI_MODEL
        if pool:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT preferred_model FROM user_settings WHERE user_id = $1",
                        message.from_user.id
                    )
                    if row:
                        current_model = row["preferred_model"]
            except Exception as e:
                logger.error(f"Ошибка при получении настроек пользователя: {e}")
        
        await message.answer(
            f"Ваша текущая модель: {current_model}\n"
            "Доступные модели: gpt-3.5-turbo, gpt-4, gpt-4o, gpt-4-turbo\n"
            "Укажите модель, например: /mode gpt-4o"
        )
        return
    
    model = command.args.strip()
    allowed_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4o", "gpt-4-turbo"]
    
    # Добавляем поддержку будущих моделей
    if model.startswith("gpt-5"):
        # Это заглушка для будущей модели GPT-5
        allowed_models.append(model)
    
    if model not in allowed_models:
        await message.answer(f"Недопустимая модель. Доступные модели: {', '.join(allowed_models)}")
        return
    
    # Сохраняем выбор модели пользователя в базе данных
    if pool:
        try:
            async with pool.acquire() as conn:
                # Проверяем, существует ли запись для этого пользователя
                existing = await conn.fetchval(
                    "SELECT 1 FROM user_settings WHERE user_id = $1",
                    message.from_user.id
                )
                
                if existing:
                    # Обновляем существующую запись
                    await conn.execute(
                        "UPDATE user_settings SET preferred_model = $1, updated_at = now() WHERE user_id = $2",
                        model, message.from_user.id
                    )
                else:
                    # Создаем новую запись
                    await conn.execute(
                        "INSERT INTO user_settings (user_id, preferred_model) VALUES ($1, $2)",
                        message.from_user.id, model
                    )
            
            await message.answer(f"✅ Модель успешно изменена на: {model}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении настроек пользователя: {e}")
            await message.answer("❌ Произошла ошибка при сохранении настроек. Попробуйте позже.")
    else:
        await message.answer("❌ База данных недоступна. Настройки не могут быть сохранены.")


@dp.message(Command("reset_context"))
async def cmd_reset_context(message: types.Message) -> None:
    """Обработчик команды /reset_context для сброса контекста диалога."""
    global pool
    
    if not pool:
        await message.answer("❌ База данных недоступна. Контекст не может быть сброшен.")
        return
    
    try:
        async with pool.acquire() as conn:
            # Удаляем историю диалога для этого пользователя
            await conn.execute(
                "DELETE FROM dialog_history WHERE user_id = $1",
                message.from_user.id
            )
        
        await message.answer("✅ Контекст диалога успешно сброшен. Начнём с чистого листа!")
    except Exception as e:
        logger.error(f"Ошибка при сбросе контекста: {e}")
        await message.answer("❌ Произошла ошибка при сбросе контекста. Попробуйте позже.")


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message) -> None:
    """Обработчик команды /admin для доступа к админ-панели."""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    
    admin_panel_text = (
        "👑 <b>Админ-панель</b>\n\n"
        "Доступные команды:\n"
        "/admin_stats - Статистика бота\n"
        "/errors - Последние ошибки\n"
        "/bot_on - Включить бота\n"
        "/bot_off - Выключить бота\n\n"
        "Используйте эти команды для управления ботом."
    )
    await message.answer(admin_panel_text)


@dp.message()
async def handle_message(message: types.Message) -> None:
    """Обработчик всех текстовых сообщений."""
    global pool
    
    # Игнорируем сообщения без текста
    if not message.text:
        return
    
    # Проверяем, активен ли бот
    if not await is_bot_active(pool):
        await message.answer("⛔ Бот временно отключён администратором.")
        return
    
    text = message.text.lower()
    
    # Если пользователь явно просит "нарисуй", "сделай картинку", "создай арт"
    image_keywords = ["картинку", "изображение", "нарисуй", "арт", "картина", "рисунок", "фото", "изобрази"]
    if any(word in text for word in image_keywords):
        try:
            # Генерируем изображение через OpenAI
            image_url = await openai_image(message.text)
            # Отправляем изображение пользователю
            await message.answer_photo(image_url, caption=f"✨ Вот что получилось!")
            
            # Записываем взаимодействие в базу
            if pool:
                try:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                            message.from_user.username,
                            "auto_art",
                            message.text,
                            f"Сгенерировано изображение: {image_url}",
                        )
                        # Сохраняем сообщение в истории диалога
                        await conn.execute(
                            "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                            message.from_user.id, "user", message.text
                        )
                        await conn.execute(
                            "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                            message.from_user.id, "assistant", f"Сгенерировано изображение: {image_url}"
                        )
                except Exception as e:
                    logger.error(f"Ошибка при записи в базу данных: {e}")
                    # Продолжаем работу, даже если не удалось записать в БД
            else:
                logger.warning("Нет подключения к базе данных, пропускаем запись лога")
            return
        except Exception as e:
            logger.error(f"Ошибка при генерации изображения: {e}")
            await message.answer("❌ Извините, произошла ошибка при генерации изображения.")
            return
    
    try:
        # Получаем выбранную пользователем модель
        user_model = None
        if pool:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT preferred_model FROM user_settings WHERE user_id = $1",
                        message.from_user.id
                    )
                    if row:
                        user_model = row["preferred_model"]
            except Exception as e:
                logger.error(f"Ошибка при получении настроек пользователя: {e}")
        
        # Получаем историю диалога
        dialog_history = []
        if pool:
            try:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT role, content FROM dialog_history WHERE user_id = $1 ORDER BY id DESC LIMIT 10",
                        message.from_user.id
                    )
                    # Переворачиваем историю, чтобы она была в хронологическом порядке
                    dialog_history = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
            except Exception as e:
                logger.error(f"Ошибка при получении истории диалога: {e}")
        
        # Добавляем текущее сообщение в историю
        dialog_history.append({"role": "user", "content": message.text})
        
        # Получаем ответ от OpenAI с учетом истории
        response = await openai_chat_with_history(DEFAULT_SYSTEM_PROMPT, dialog_history, user_model)
        
        # Усечение длинных ответов для Telegram
        if len(response) > settings.MAX_TG_REPLY:
            response = response[: settings.MAX_TG_REPLY] + "... (ответ усечён)"
        
        # Отправляем ответ пользователю
        await message.answer(response)
        
        # Записываем взаимодействие в базу
        if pool:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                        message.from_user.username,
                        "message",
                        message.text,
                        response,
                    )
                    # Сохраняем сообщение в истории диалога
                    await conn.execute(
                        "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                        message.from_user.id, "user", message.text
                    )
                    await conn.execute(
                        "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                        message.from_user.id, "assistant", response
                    )
            except Exception as e:
                logger.error(f"Ошибка при записи в базу данных: {e}")
                # Продолжаем работу, даже если не удалось записать в БД
        else:
            logger.warning("Нет подключения к базе данных, пропускаем запись лога")
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await message.answer("❌ Извините, произошла ошибка при обработке вашего сообщения.")


async def main() -> None:
    """Основная функция запуска бота."""
    # Регистрируем обработчики запуска и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    # Запускаем polling (опрос)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
