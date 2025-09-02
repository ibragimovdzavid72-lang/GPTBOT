"""
Основной модуль Telegram‑бота с поддержкой команды /suggest_prompt и логированием.

Этот модуль использует библиотеку aiogram v3 для асинхронной работы с
Telegram‑API, а также асинхронный драйвер asyncpg для записи логов в
PostgreSQL. Он подключается к OpenAI через модуль ai для генерации
ответов на сообщения пользователей.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

from .config import settings
from .suggest import generate_prompt_from_logs
from .ai import openai_chat, openai_image


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
Добро пожаловать!
🧠 Ваш AI Agent

🤖 Мультимодельный AI (GPT-4o)
• 🎨 Генерация изображений  
• 📊 Продвинутая аналитика
• 💎 Персонализация

💫 Начните прямо сейчас:
Просто напишите любой вопрос и испытайте мощь современного AI!

🎯 Команды:
/help - Подробная помощь
/stats - Ваша статистика
/suggest_prompt - Улучшенный промпт
/art - Создать изображение
"""

# Создание главного меню с кнопками
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🧠 Умный чат", callback_data="chat")],
    [InlineKeyboardButton(text="🎨 Создать арт", callback_data="art")],
    [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
    [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
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
                        WHERE table_name = 'logs' OR table_name = 'bot_config'
                    )
                """)
                
                if not tables_exist:
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
    await message.answer(WELCOME_TEXT, reply_markup=main_menu)


@dp.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Обработчик команды /help."""
    help_text = (
        "ℹ️ <b>Доступные команды:</b>\n"
        "/start - Главное меню\n"
        "/help - Показать справку\n"
        "/stats - Показать статистику\n"
        "/suggest_prompt - Предложить улучшенный промпт\n"
        "/art - Создать изображение по описанию\n\n"
        "Используйте кнопки меню для быстрого доступа к функциям."
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
    elif callback_query.data == "help":
        # Вызываем обработчик команды /help
        await cmd_help(callback_query.message)


@dp.message()
async def handle_message(message: types.Message) -> None:
    """Обработчик всех текстовых сообщений."""
    # Игнорируем сообщения без текста
    if not message.text:
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
        # Получаем ответ от OpenAI
        response = await openai_chat(DEFAULT_SYSTEM_PROMPT, message.text)
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
