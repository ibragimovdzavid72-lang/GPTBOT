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
from .ai import openai_chat, openai_image, openai_vision, openai_tts, openai_stt, openai_chat_with_history
from .admin import is_admin, cmd_admin_stats, cmd_errors, cmd_bot_on, cmd_bot_off, is_bot_active
from .webhook import WebhookManager

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

🚀 Используйте кнопки ниже для быстрого доступа к всем функциям!
Или просто напишите любой вопрос и получите умные ответы от современного AI!
"""

# Создание главного меню с кнопками для всех команд
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
     InlineKeyboardButton(text="🎨 Создать арт", callback_data="art")],
    [InlineKeyboardButton(text="💡 Умный промпт", callback_data="suggest_prompt"),
     InlineKeyboardButton(text="🔄 Сброс контекста", callback_data="reset_context")],
    [InlineKeyboardButton(text="🤖 Модель ИИ", callback_data="select_model"),
     InlineKeyboardButton(text="🔊 Голосовые ответы", callback_data="tts_settings")],
    [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help"),
     InlineKeyboardButton(text="💬 Начать чат", callback_data="chat")],
])

# Создание расширенного меню с админ-панелью для администраторов
admin_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
     InlineKeyboardButton(text="🎨 Создать арт", callback_data="art")],
    [InlineKeyboardButton(text="💡 Умный промпт", callback_data="suggest_prompt"),
     InlineKeyboardButton(text="🔄 Сброс контекста", callback_data="reset_context")],
    [InlineKeyboardButton(text="🤖 Модель ИИ", callback_data="select_model"),
     InlineKeyboardButton(text="🔊 Голосовые ответы", callback_data="tts_settings")],
    [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help"),
     InlineKeyboardButton(text="💬 Начать чат", callback_data="chat")],
    [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")],
])

# Меню админских команд
admin_commands_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Админ статистика", callback_data="admin_stats"),
     InlineKeyboardButton(text="⚠️ Ошибки", callback_data="errors")],
    [InlineKeyboardButton(text="✅ Включить бота", callback_data="bot_on"),
     InlineKeyboardButton(text="❌ Выключить бота", callback_data="bot_off")],
    [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")],
])

# Создание меню настроек

model_selection_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="GPT-4o", callback_data="set_model_gpt-4o")],
    [InlineKeyboardButton(text="GPT-4 Turbo", callback_data="set_model_gpt-4-turbo")],
    [InlineKeyboardButton(text="GPT-3.5 Turbo", callback_data="set_model_gpt-3.5-turbo")],
    [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")],
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
        "ℹ️ <b>Интерфейс бота:</b>\n\n"
        "🚀 <b>Основной способ управления:</b>\n"
        "Используйте кнопки меню для быстрого доступа к всем функциям!\n\n"
        "🎯 <b>Доступные команды (опционально):</b>\n"
        "/start - Главное меню\n"
        "/help - Показать справку\n"
        "/stats - Показать статистику\n"
        "/suggest_prompt - Предложить улучшенный промпт\n"
        "/art - Создать изображение по описанию\n"
        "/mode - Выбрать модель ИИ\n"
        "/reset_context - Сбросить контекст диалога\n\n"
        "💬 <b>Общение:</b> Просто напишите сообщение, отправьте голосовое сообщение или изображение!"
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
        await callback_query.message.answer("💬 Просто отправьте мне сообщение, и я отвечу!")
    elif callback_query.data == "stats":
        # Вызываем обработчик команды /stats
        await cmd_stats(callback_query.message)
    elif callback_query.data == "art":
        # Просим ввести описание для генерации арта
        await callback_query.message.answer("🎨 <b>Создание изображения</b>\n\nОпишите, что вы хотите нарисовать:\n\nПример: котенок на скейте в очках")
    elif callback_query.data == "suggest_prompt":
        # Вызываем обработчик команды /suggest_prompt
        await cmd_suggest_prompt(callback_query.message)
    elif callback_query.data == "reset_context":
        # Вызываем команду сброса контекста
        await cmd_reset_context(callback_query.message)
        # Возвращаемся в главное меню
        if is_admin(callback_query.from_user.id):
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=admin_menu)
        else:
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=main_menu)
    elif callback_query.data == "help":
        # Вызываем обработчик команды /help
        await cmd_help(callback_query.message)
    elif callback_query.data == "admin_panel":
        # Проверяем, является ли пользователь администратором
        if is_admin(callback_query.from_user.id):
            await callback_query.message.answer("👑 <b>Админ-панель</b>", reply_markup=admin_commands_menu)
        else:
            await callback_query.message.answer("⛔ У вас нет доступа к админ-панели.")
    elif callback_query.data == "select_model":
        await callback_query.message.answer("🤖 <b>Выберите модель ИИ</b>", reply_markup=model_selection_menu)
    elif callback_query.data == "tts_settings":
        # Показываем текущие настройки TTS и предлагаем изменить
        await show_tts_settings(callback_query.message)
    elif callback_query.data == "toggle_tts":
        # Переключаем настройки TTS
        await toggle_tts(callback_query.message)
        await show_tts_settings(callback_query.message)
    elif callback_query.data == "change_tts_voice":
        # Показываем меню выбора голоса
        voice_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Alloy", callback_data="set_voice_alloy")],
            [InlineKeyboardButton(text="Echo", callback_data="set_voice_echo")],
            [InlineKeyboardButton(text="Fable", callback_data="set_voice_fable")],
            [InlineKeyboardButton(text="Onyx", callback_data="set_voice_onyx")],
            [InlineKeyboardButton(text="Nova", callback_data="set_voice_nova")],
            [InlineKeyboardButton(text="Shimmer", callback_data="set_voice_shimmer")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="tts_settings")],
        ])
        await callback_query.message.answer("🗣 <b>Выберите голос</b>", reply_markup=voice_menu)
    elif callback_query.data.startswith("set_voice_"):
        # Устанавливаем голос TTS
        voice = callback_query.data.replace("set_voice_", "")
        await set_tts_voice(callback_query.message, voice)
        await show_tts_settings(callback_query.message)
    # Админские команды
    elif callback_query.data == "admin_stats":
        if is_admin(callback_query.from_user.id):
            await cmd_admin_stats(callback_query.message, pool)
        else:
            await callback_query.message.answer("⛔ У вас нет доступа к этой команде.")
    elif callback_query.data == "errors":
        if is_admin(callback_query.from_user.id):
            await cmd_errors(callback_query.message, pool)
        else:
            await callback_query.message.answer("⛔ У вас нет доступа к этой команде.")
    elif callback_query.data == "bot_on":
        if is_admin(callback_query.from_user.id):
            await cmd_bot_on(callback_query.message, pool)
        else:
            await callback_query.message.answer("⛔ У вас нет доступа к этой команде.")
    elif callback_query.data == "bot_off":
        if is_admin(callback_query.from_user.id):
            await cmd_bot_off(callback_query.message, pool)
        else:
            await callback_query.message.answer("⛔ У вас нет доступа к этой команде.")
    elif callback_query.data == "back_to_main":
        # Возвращаемся в главное меню
        if is_admin(callback_query.from_user.id):
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=admin_menu)
        else:
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=main_menu)
    elif callback_query.data == "back_to_settings":
        # Не нужно, так как settings_menu убрано
        if is_admin(callback_query.from_user.id):
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=admin_menu)
        else:
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=main_menu)
    elif callback_query.data.startswith("set_model_"):
        # Устанавливаем модель ИИ
        model = callback_query.data.replace("set_model_", "")
        await set_user_model(callback_query.message, model)
        await callback_query.message.answer(f"✅ Модель ИИ успешно изменена на {model}!")
        # Возвращаемся в главное меню
        if is_admin(callback_query.from_user.id):
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=admin_menu)
        else:
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=main_menu)


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
    # Показываем меню выбора модели
    await message.answer("🤖 <b>Выберите модель ИИ</b>", reply_markup=model_selection_menu)


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
    
    # Обрабатываем голосовые сообщения
    if message.voice:
        await handle_voice_message(message)
        return
    
    # Обрабатываем изображения
    if message.photo:
        await handle_image_message(message)
        return
    
    # Обрабатываем текстовые сообщения
    await process_text_message(message)


async def handle_voice_message(message: types.Message) -> None:
    """Обработчик голосовых сообщений."""
    global pool
    
    # Проверяем, активен ли бот
    if not await is_bot_active(pool):
        await message.answer("⛔ Бот временно отключён администратором.")
        return
    
    try:
        # Получаем файл голосового сообщения
        file_info = await bot.get_file(message.voice.file_id)
        file_path = file_info.file_path
        
        # Скачиваем голосовое сообщение
        file_url = f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}"
        
        # Создаем временное имя файла
        import tempfile
        import aiohttp
        import os
        
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
            temp_filename = temp_file.name
            
        # Скачиваем файл
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status == 200:
                    with open(temp_filename, 'wb') as f:
                        f.write(await response.read())
                else:
                    raise Exception(f"Не удалось скачать голосовое сообщение: {response.status}")
        
        # Распознаем речь с помощью OpenAI Whisper
        recognized_text = await openai_stt(temp_filename)
        
        # Удаляем временный файл
        os.unlink(temp_filename)
        
        # Отправляем пользователю распознанный текст для подтверждения
        await message.answer(f"🎤 Распознанный текст:\n\n{recognized_text}\n\nОбрабатываю ваш запрос...")
        
        # Обрабатываем распознанный текст как обычное сообщение
        # Создаем фиктивное сообщение с распознанным текстом
        from dataclasses import dataclass
        from typing import Optional
        
        @dataclass
        class FakeMessage:
            text: str
            from_user: object
            chat: object
            message_id: int
            
            def __init__(self, original_message, text):
                self.text = text
                self.from_user = original_message.from_user
                self.chat = original_message.chat
                self.message_id = original_message.message_id
        
        fake_message = FakeMessage(message, recognized_text)
        
        # Обрабатываем как обычное текстовое сообщение
        await process_text_message(fake_message)
        
    except Exception as e:
        logger.error(f"Ошибка при обработке голосового сообщения: {e}")
        await message.answer("❌ Извините, произошла ошибка при распознавании голосового сообщения.")


async def set_user_model(message: types.Message, model: str) -> None:
    """Устанавливает предпочитаемую модель ИИ для пользователя."""
    global pool
    
    if not pool:
        await message.answer("❌ База данных недоступна. Настройки не могут быть сохранены.")
        return
    
    try:
        async with pool.acquire() as conn:
            # Проверяем, есть ли уже настройки пользователя
            existing = await conn.fetchrow(
                "SELECT user_id FROM user_settings WHERE user_id = $1",
                message.from_user.id
            )
            
            if existing:
                # Обновляем существующие настройки
                await conn.execute(
                    "UPDATE user_settings SET preferred_model = $1, updated_at = now() WHERE user_id = $2",
                    model, message.from_user.id
                )
            else:
                # Создаем новые настройки с всеми полями по умолчанию
                await conn.execute(
                    "INSERT INTO user_settings (user_id, preferred_model, tts_enabled, tts_voice) VALUES ($1, $2, $3, $4)",
                    message.from_user.id, model, False, "alloy"
                )
        
        logger.info(f"Пользователь {message.from_user.id} изменил модель на {model}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении модели пользователя: {e}")
        await message.answer("❌ Произошла ошибка при сохранении настроек. Попробуйте позже.")


async def show_tts_settings(message: types.Message) -> None:
    """Показывает текущие настройки TTS."""
    global pool
    
    tts_enabled = False
    tts_voice = "alloy"
    
    if pool:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT tts_enabled, tts_voice FROM user_settings WHERE user_id = $1",
                    message.from_user.id
                )
                if row:
                    tts_enabled = row["tts_enabled"]
                    tts_voice = row["tts_voice"]
        except Exception as e:
            logger.error(f"Ошибка при получении настроек TTS: {e}")
    
    status = "Включены" if tts_enabled else "Выключены"
    tts_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔊 Голосовые ответы: {status}", callback_data="toggle_tts")],
        [InlineKeyboardButton(text=f"🗣 Голос: {tts_voice.title()}", callback_data="change_tts_voice")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")],
    ])
    
    await message.answer("🔊 <b>Настройки голосовых ответов</b>", reply_markup=tts_menu)


async def toggle_tts(message: types.Message) -> None:
    """Переключает настройки TTS."""
    global pool
    
    if not pool:
        await message.answer("❌ База данных недоступна. Настройки не могут быть сохранены.")
        return
    
    try:
        async with pool.acquire() as conn:
            # Получаем текущие настройки
            row = await conn.fetchrow(
                "SELECT tts_enabled FROM user_settings WHERE user_id = $1",
                message.from_user.id
            )
            
            current_tts = False
            if row:
                current_tts = row["tts_enabled"]
            
            new_tts = not current_tts
            
            # Проверяем, есть ли уже настройки пользователя
            existing = await conn.fetchrow(
                "SELECT user_id FROM user_settings WHERE user_id = $1",
                message.from_user.id
            )
            
            if existing:
                # Обновляем существующие настройки
                await conn.execute(
                    "UPDATE user_settings SET tts_enabled = $1, updated_at = now() WHERE user_id = $2",
                    new_tts, message.from_user.id
                )
            else:
                # Создаем новые настройки с всеми полями по умолчанию
                await conn.execute(
                    "INSERT INTO user_settings (user_id, tts_enabled, preferred_model, tts_voice, created_at, updated_at) VALUES ($1, $2, $3, $4, now(), now())",
                    message.from_user.id, new_tts, "gpt-4o", "alloy"
                )
                # Создаем новые настройки с всеми полями по умолчанию
                await conn.execute(
                    "INSERT INTO user_settings (user_id, tts_enabled, preferred_model, tts_voice) VALUES ($1, $2, $3, $4)",
                    message.from_user.id, new_tts, "gpt-4o", "alloy"
                )
        
        status = "включены" if new_tts else "выключены"
        logger.info(f"Пользователь {message.from_user.id} изменил TTS на {status}")
    except Exception as e:
        logger.error(f"Ошибка при переключении TTS: {e}")
        await message.answer("❌ Произошла ошибка при изменении настроек. Попробуйте позже.")


async def set_tts_voice(message: types.Message, voice: str) -> None:
    """Устанавливает голос для TTS."""
    global pool
    
    if not pool:
        await message.answer("❌ База данных недоступна. Настройки не могут быть сохранены.")
        return
    
    try:
        async with pool.acquire() as conn:
            # Проверяем, есть ли уже настройки пользователя
            existing = await conn.fetchrow(
                "SELECT user_id FROM user_settings WHERE user_id = $1",
                message.from_user.id
            )
            
            if existing:
                # Обновляем существующие настройки
                await conn.execute(
                    "UPDATE user_settings SET tts_voice = $1, updated_at = now() WHERE user_id = $2",
                    voice, message.from_user.id
                )
            else:
                # Создаем новые настройки с всеми полями по умолчанию
                await conn.execute(
                    "INSERT INTO user_settings (user_id, tts_voice, preferred_model, tts_enabled, created_at, updated_at) VALUES ($1, $2, $3, $4, now(), now())",
                    message.from_user.id, voice, "gpt-4o", False
                )
        
        logger.info(f"Пользователь {message.from_user.id} изменил голос TTS на {voice}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении голоса TTS: {e}")
        await message.answer("❌ Произошла ошибка при сохранении настроек. Попробуйте позже.")


async def handle_image_message(message: types.Message) -> None:
    """Обработчик сообщений с изображениями."""
    global pool
    
    # Проверяем, активен ли бот
    if not await is_bot_active(pool):
        await message.answer("⛔ Бот временно отключён администратором.")
        return
    
    try:
        # Получаем самое большое изображение из присланных
        photo = message.photo[-1]
        
        # Получаем файл изображения
        file_info = await bot.get_file(photo.file_id)
        file_path = file_info.file_path
        
        # Создаем URL для скачивания
        file_url = f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}"
        
        # Получаем текст сообщения (если есть)
        caption = message.caption or "Что изображено на этой картинке?"
        
        await message.answer("👀 Анализирую изображение...")
        
        # Скачиваем файл изображения
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Не удалось скачать изображение: {resp.status}")
                image_data = await resp.read()
        
        # Анализируем изображение через OpenAI Vision
        response = await openai_vision(image_data, caption)
        
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
                        "vision",
                        caption,
                        response,
                    )
                    # Сохраняем в истории диалога
                    await conn.execute(
                        "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                        message.from_user.id, "user", f"[Изображение] {caption}"
                    )
                    await conn.execute(
                        "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                        message.from_user.id, "assistant", response
                    )
            except Exception as e:
                logger.error(f"Ошибка при записи в базу данных: {e}")
        else:
            logger.warning("Нет подключения к базе данных, пропускаем запись лога")
    
    except Exception as e:
        logger.error(f"Ошибка при анализе изображения: {e}")
        await message.answer("❌ Извините, произошла ошибка при анализе изображения.")


async def process_text_message(message) -> None:
    """Обрабатывает текстовое сообщение (обычное или из голосового)."""
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
        # Проверяем, включены ли голосовые ответы
        tts_enabled = False
        tts_voice = "alloy"
        if pool:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT tts_enabled, tts_voice FROM user_settings WHERE user_id = $1",
                        message.from_user.id
                    )
                    if row:
                        tts_enabled = row["tts_enabled"]
                        tts_voice = row["tts_voice"]
            except Exception as e:
                logger.error(f"Ошибка при получении настроек TTS: {e}")
        
        if tts_enabled and len(response) < 4000:  # Ограничение на длину для TTS
            try:
                # Генерируем голосовое сообщение
                audio_content = await openai_tts(response, tts_voice)
                
                # Создаем временный файл для аудио
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                    temp_filename = temp_file.name
                    temp_file.write(audio_content)
                
                # Отправляем голосовое сообщение
                from aiogram.types import FSInputFile
                audio = FSInputFile(temp_filename, filename="response.mp3")
                await message.answer_voice(audio, caption=response[:1000] + "..." if len(response) > 1000 else response)
                
                # Удаляем временный файл
                os.unlink(temp_filename)
            except Exception as e:
                logger.error(f"Ошибка при генерации голосового ответа: {e}")
                # Отправляем текстовый ответ в случае ошибки
                await message.answer(response)
        else:
            # Отправляем текстовый ответ
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
    """Главная функция для запуска бота."""
    import os
    
    logger.info("Запуск Telegram-бота...")
    
    # Настройка хендлеров запуска и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Проверяем режим работы: webhook или polling
    webhook_url = os.getenv("WEBHOOK_URL")
    use_webhook = webhook_url is not None
    
    if use_webhook:
        logger.info(f"🌐 Используется WEBHOOK режим: {webhook_url}")
        try:
            # Создаем webhook менеджер
            webhook_manager = WebhookManager(bot, dp)
            
            # Запускаем webhook сервер
            runner = await webhook_manager.run_webhook_server()
            
            logger.info("✅ Webhook сервер запущен успешно!")
            
            # Ожидаем завершения
            try:
                while True:
                    await asyncio.sleep(3600)  # Просыпаемся 1 час
            except KeyboardInterrupt:
                logger.info("👋 Бот остановлен пользователем")
            finally:
                # Останавливаем сервер
                await runner.cleanup()
                await webhook_manager.remove_webhook()
                
        except Exception as e:
            logger.error(f"💥 Ошибка в webhook режиме: {e}")
            logger.info("🔄 Переходим на polling режим...")
            use_webhook = False
    
    if not use_webhook:
        logger.info("🔄 Используется POLLING режим")
        try:
            # Запуск бота в polling режиме
            await dp.start_polling(bot, skip_updates=True)
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен пользователем")
        except Exception as e:
            logger.error(f"💥 Критическая ошибка при запуске бота: {e}")
        finally:
            logger.info("🏁 Завершение работы бота...")


if __name__ == "__main__":
    # Запуск бота
    asyncio.run(main())
