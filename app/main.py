"""
Основной модуль Telegram‑бота с поддержкой команды /suggest_prompt и логированием.

Этот модуль использует библиотеку aiogram v3 для асинхронной работы с
Telegram‑API, а также асинхронный драйвер asyncpg для записи логов в
PostgreSQL. Он подключается к OpenAI через модуль ai для генерации
ответов на сообщения пользователей.
"""

import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

from .config import settings
from .suggest import generate_prompt_from_logs
from .ai import openai_chat, openai_image, openai_vision, openai_tts, openai_stt, openai_chat_with_history, openai_chat_with_personal_context
from .admin import is_admin, cmd_admin_stats, cmd_errors, cmd_bot_on, cmd_bot_off, is_bot_active
from .webhook import WebhookManager
from .vector_memory import personal_assistant

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

# Кеш для хранения распознанных голосовых сообщений
voice_messages_cache = {}

# Кеш для хранения описаний изображений для генерации арта
art_prompts_cache = {}

# Кеш для хранения выбранных размеров арта пользователей
user_art_sizes = {}

# Состояния пользователей для обработки персонального ассистента
user_states = {}

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

# Создание главного меню с категоризацией функций
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💬 ИИ Чат", callback_data="ai_chat_menu"),
     InlineKeyboardButton(text="🎨 Творчество", callback_data="creative_menu")],
    [InlineKeyboardButton(text="📊 Аналитика", callback_data="analytics_menu"),
     InlineKeyboardButton(text="🔧 Настройки", callback_data="settings_menu")],
    [InlineKeyboardButton(text="🧠 Личный ассистент", callback_data="personal_assistant"),
     InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
])

# Расширенное меню для администраторов
admin_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💬 ИИ Чат", callback_data="ai_chat_menu"),
     InlineKeyboardButton(text="🎨 Творчество", callback_data="creative_menu")],
    [InlineKeyboardButton(text="📊 Аналитика", callback_data="analytics_menu"),
     InlineKeyboardButton(text="🔧 Настройки", callback_data="settings_menu")],
    [InlineKeyboardButton(text="🧠 Личный ассистент", callback_data="personal_assistant"),
     InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")],
    [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
])

# Меню ИИ Чата
ai_chat_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💬 Начать чат", callback_data="start_chat"),
     InlineKeyboardButton(text="🤖 Выбрать модель", callback_data="select_model")],
    [InlineKeyboardButton(text="🔄 Сбросить контекст", callback_data="reset_context"),
     InlineKeyboardButton(text="💡 Умный промпт", callback_data="suggest_prompt")],
    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_to_main")],
])

# Меню творчества
creative_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎨 Создать изображение", callback_data="create_image")],
    [InlineKeyboardButton(text="🖼️ Анализ изображений", callback_data="image_analysis_info")],
    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_to_main")],
])

# Меню аналитики
analytics_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Общая статистика", callback_data="stats")],
    [InlineKeyboardButton(text="📈 Моя активность", callback_data="user_stats")],
    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_to_main")],
])

# Меню настроек
settings_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🤖 Модель ИИ", callback_data="select_model"),
     InlineKeyboardButton(text="🔊 Голосовые ответы", callback_data="tts_settings")],
    [InlineKeyboardButton(text="🌐 Язык интерфейса", callback_data="language_settings"),
     InlineKeyboardButton(text="🔔 Уведомления", callback_data="notification_settings")],
    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_to_main")],
])

# Меню админских команд
admin_commands_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Админ статистика", callback_data="admin_stats"),
     InlineKeyboardButton(text="⚠️ Ошибки системы", callback_data="errors")],
    [InlineKeyboardButton(text="✅ Включить бота", callback_data="bot_on"),
     InlineKeyboardButton(text="❌ Выключить бота", callback_data="bot_off")],
    [InlineKeyboardButton(text="🔧 Управление", callback_data="admin_management"),
     InlineKeyboardButton(text="📋 Логи системы", callback_data="admin_logs")],
    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_to_main")],
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
    """Обработчик команды /start - единственная оставшаяся слэш команда."""
    # Формируем персонализированное приветствие
    username = message.from_user.username or message.from_user.first_name or "Пользователь"
    current_date = datetime.now().strftime("%d.%m.%Y")
    
    welcome_text = WELCOME_TEXT.format(username=username, date=current_date)
    
    # Показываем расширенное меню для администраторов
    if is_admin(message.from_user.id):
        await message.answer(welcome_text, reply_markup=admin_menu)
    else:
        await message.answer(welcome_text, reply_markup=main_menu)


# ============================================================================
# УДАЛЕНО: Все слэш команды заменены на инлайн кнопки
# /help, /stats, /suggest_prompt, /art, /mode, /reset_context, 
# /personal, /admin, /admin_stats, /errors, /bot_on, /bot_off
# Теперь все функции доступны через интуитивные меню
# ============================================================================

# Вспомогательные функции для callback обработчиков

async def show_user_personal_stats(message: types.Message, user_id: int) -> None:
    """Показывает персональную статистику пользователя."""
    global pool
    
    if not pool:
        await message.answer("⛔ База данных недоступна.")
        return
    
    try:
        async with pool.acquire() as conn:
            user_logs = await conn.fetchval(
                "SELECT COUNT(*) FROM logs WHERE username = $1",
                message.from_user.username or str(user_id)
            )
            
            user_settings = await conn.fetchrow(
                "SELECT preferred_model, tts_enabled, personal_assistant_enabled FROM user_settings WHERE user_id = $1",
                user_id
            )
            
        stats_text = f"📈 <b>Моя активность</b>\n\n"
        stats_text += f"💬 Сообщений: {user_logs}\n"
        
        if user_settings:
            stats_text += f"🤖 Модель: {user_settings['preferred_model'] or 'gpt-4o'}\n"
            stats_text += f"🔊 TTS: {'\u2705' if user_settings['tts_enabled'] else '\u274c'}\n"
            stats_text += f"🧠 Личный ассистент: {'\u2705' if user_settings['personal_assistant_enabled'] else '\u274c'}\n"
        
        pa_stats = await personal_assistant.get_user_stats(user_id)
        if pa_stats.get("total_memories", 0) > 0:
            stats_text += f"\n🧠 Память: {pa_stats['total_memories']} записей"
        
        await message.answer(stats_text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await message.answer("❌ Ошибка получения статистики.")


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
    """Улучшенный обработчик команды /art для генерации изображений с выбором размера."""
    # Извлекаем текст описания изображения
    text = message.text.replace("/art", "").strip()
    
    if not text:
        size_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 512x512 (быстро)", callback_data="art_size_512")],
            [InlineKeyboardButton(text="🖼️ 1024x1024 (качество)", callback_data="art_size_1024")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]
        ])
        await message.answer(
            "🎨 <b>Создание изображения</b>\n\nОпишите, что вы хотите нарисовать:\n\n🎆 <i>Пример: котенок на скейте в очках, стиль аниме</i>\n\nВыберите размер изображения:",
            reply_markup=size_menu,
            parse_mode="HTML"
        )
        return
        
    await generate_art_image(message, text)


@dp.callback_query()
async def process_callback(callback_query: types.CallbackQuery) -> None:
    """Обработчик нажатий на кнопки меню."""
    await callback_query.answer()
    
    # 📂 Навигация по категориям меню
    if callback_query.data == "ai_chat_menu":
        await callback_query.message.answer("💬 <b>ИИ Чат</b>\n\nВыберите действие:", reply_markup=ai_chat_menu, parse_mode="HTML")
    elif callback_query.data == "creative_menu":
        await callback_query.message.answer("🎨 <b>Творчество</b>\n\nИскусство и создание:", reply_markup=creative_menu, parse_mode="HTML")
    elif callback_query.data == "analytics_menu":
        await callback_query.message.answer("📊 <b>Аналитика</b>\n\nСтатистика и анализ:", reply_markup=analytics_menu, parse_mode="HTML")
    elif callback_query.data == "settings_menu":
        await callback_query.message.answer("🔧 <b>Настройки</b>\n\nПерсонализация работы бота:", reply_markup=settings_menu, parse_mode="HTML")
    
    # 💬 Обработчики ИИ чата
    elif callback_query.data == "start_chat":
        await callback_query.message.answer("💬 Просто напишите мне сообщение, и я отвечу!\n\n🎤 Можно также отправить голосовое сообщение или изображение.")
    
    # 🎨 Обработчики творчества
    elif callback_query.data == "create_image":
        size_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 512x512 (быстро)", callback_data="art_size_512")],
            [InlineKeyboardButton(text="🖼️ 1024x1024 (качество)", callback_data="art_size_1024")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="creative_menu")]
        ])
        await callback_query.message.answer(
            "🎨 <b>Создание изображения</b>\n\nОпишите, что вы хотите нарисовать:\n\n🎆 <i>Пример: котенок на скейте в очках, стиль аниме</i>\n\nВыберите размер изображения:",
            reply_markup=size_menu,
            parse_mode="HTML"
        )
    elif callback_query.data == "image_analysis_info":
        await callback_query.message.answer(
            "🖼️ <b>Анализ изображений</b>\n\n"
            "🔍 Просто отправьте мне изображение, и я:\n\n"
            "• Опишу что на нём изображено\n"
            "• Отвечу на вопросы о контенте\n"
            "• Помогу с анализом и интерпретацией\n\n"
            "📷 Поддерживаются все популярные форматы изображений.",
            parse_mode="HTML"
        )
    
    # 📊 Обработчики аналитики
    elif callback_query.data == "user_stats":
        await show_user_personal_stats(callback_query.message, callback_query.from_user.id)
    
    # 🔧 Обработчики настроек
    elif callback_query.data == "language_settings":
        language_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"),
             InlineKeyboardButton(text="🇺🇸 English", callback_data="set_lang_en")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_menu")]
        ])
        await callback_query.message.answer(
            "🌐 <b>Язык интерфейса</b>\n\nВыберите язык:",
            reply_markup=language_menu,
            parse_mode="HTML"
        )
    elif callback_query.data == "notification_settings":
        await callback_query.message.answer(
            "🔔 <b>Уведомления</b>\n\n"
            "Эта функция будет доступна в следующих обновлениях.",
            parse_mode="HTML"
        )
    elif callback_query.data.startswith("set_lang_"):
        lang = callback_query.data.replace("set_lang_", "")
        lang_names = {"ru": "Русский", "en": "English"}
        await callback_query.message.answer(f"✅ Язык установлен: {lang_names.get(lang, lang)}")
    elif callback_query.data == "reset_context":
        # Вызываем команду сброса контекста
        await cmd_reset_context(callback_query.message)
        # Возвращаемся в главное меню
        if is_admin(callback_query.from_user.id):
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=admin_menu)
        else:
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=main_menu)
    elif callback_query.data == "help":
        # Отображаем обновлённую справку
        help_text = (
            "ℹ️ <b>Интерфейс бота:</b>\n\n"
            "🎆 <b>Как пользоваться:</b>\n"
            "• Навигация по кнопкам меню\n"
            "• Простое общение текстом\n"
            "• Голосовые сообщения\n"
            "• Отправка изображений\n\n"
            "📋 <b>Основные разделы:</b>\n"
            "💬 ИИ Чат - Общение с ИИ\n"
            "🎨 Творчество - Создание изображений\n"
            "📊 Аналитика - Статистика использования\n"
            "🔧 Настройки - Персонализация\n"
            "🧠 Личный ассистент - Векторная память\n\n"
            "🚀 <b>Начните с /start</b> для возвращения в главное меню!"
        )
        
        # Добавляем информацию об админских возможностях
        if is_admin(callback_query.from_user.id):
            help_text += (
                "\n\n👑 <b>Админ-возможности:</b>\n"
                "• Мониторинг системы\n"
                "• Управление ботом\n"
                "• Просмотр ошибок"
            )
        
        await callback_query.message.answer(help_text, parse_mode="HTML")
    elif callback_query.data == "admin_panel":
        # Проверяем, является ли пользователь администратором с расширенным логированием
        user_id = callback_query.from_user.id
        admins_raw = os.getenv("ADMINS", "")
        logger.info(f"👑 ДИАГНОСТИКА АДМИН ДОСТУПА:")
        logger.info(f"   user_id={user_id} (тип: {type(user_id)})")
        logger.info(f"   ADMINS env={repr(admins_raw)}")
        logger.info(f"   ADMINS parsed={settings.ADMINS}")
        logger.info(f"   ADMINS types={[type(x) for x in settings.ADMINS]}")
        
        if is_admin(user_id):
            logger.info(f"✅ Админский доступ РАЗРЕШЁН для user_id={user_id}")
            await callback_query.message.answer("👑 <b>Админ-панель</b>", reply_markup=admin_commands_menu)
        else:
            logger.warning(f"❌ Админский доступ ЗАПРЕЩЁН для user_id={user_id}")
            logger.warning(f"💡 Чтобы получить доступ, добавьте {user_id} в переменную ADMINS")
            await callback_query.message.answer(f"⛔ У вас нет доступа к админ-панели.\n\n📝 Ваш ID: {user_id}\n\n💡 Для получения доступа обратитесь к администратору.")
    elif callback_query.data == "select_model":
        await callback_query.message.answer("🤖 <b>Выберите модель ИИ</b>", reply_markup=model_selection_menu)
    elif callback_query.data == "personal_assistant":
        # Показываем меню персонального ассистента
        await show_personal_assistant_menu(callback_query.message, callback_query.from_user.id)
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
    elif callback_query.data.startswith("voice_response_"):
        # Отвечаем голосом на распознанное сообщение
        await callback_query.message.answer("🔊 Готовлю голосовой ответ...")
        
        # Извлекаем ключ из callback_data
        key = callback_query.data.replace("voice_response_", "")
        recognized_text = voice_messages_cache.get(key)
        
        if recognized_text:
            await process_voice_text_message(callback_query, recognized_text, voice_response=True)
            # Очищаем кеш
            voice_messages_cache.pop(key, None)
        else:
            await callback_query.message.answer("❌ Не удалось найти распознанный текст. Попробуйте отправить голосовое сообщение снова.")
            
    elif callback_query.data.startswith("text_response_"):
        # Обычный текстовый ответ
        await callback_query.message.answer("📝 Обрабатываю ваш запрос...")
        
        # Извлекаем ключ из callback_data
        key = callback_query.data.replace("text_response_", "")
        recognized_text = voice_messages_cache.get(key)
        
        if recognized_text:
            await process_voice_text_message(callback_query, recognized_text, voice_response=False)
            # Очищаем кеш
            voice_messages_cache.pop(key, None)
        else:
            await callback_query.message.answer("❌ Не удалось найти распознанный текст. Попробуйте отправить голосовое сообщение снова.")
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
    
    # 🎨 Обработчики для генерации изображений
    elif callback_query.data.startswith("art_size_"):
        # Выбор размера для генерации арта
        size = callback_query.data.replace("art_size_", "")
        size_map = {"512": "512x512", "1024": "1024x1024"}
        actual_size = size_map.get(size, "1024x1024")
        
        await callback_query.message.answer(
            f"🎨 Опишите, что вы хотите нарисовать:\n\n📏 Размер: {actual_size}\n\n🎆 <i>Пример: котенок на скейте в очках, стиль аниме</i>",
            parse_mode="HTML"
        )
        # Сохраняем выбранный размер для следующего сообщения
        user_art_sizes[callback_query.from_user.id] = actual_size
        
    elif callback_query.data.startswith("generate_similar_"):
        # Генерация похожего арта на основе описания изображения
        key = callback_query.data.replace("generate_similar_", "")
        description = art_prompts_cache.get(key)
        
        if description:
            await bot.send_chat_action(callback_query.message.chat.id, "upload_photo")
            processing_msg = await callback_query.message.answer("🎨 Создаю похожее изображение...")
            
            # Улучшаем промпт для генерации арта
            art_prompt = f"Прекрасное художественное изображение: {description}, высокое качество, детализированное"
            
            try:
                image_url = await openai_image(art_prompt)
                await processing_msg.delete()
                
                art_menu = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Генерировать ещё", callback_data=f"regenerate_art_{hash(art_prompt)%10000}")],
                    [InlineKeyboardButton(text="🔄 Сбросить диалог", callback_data="reset_context")]
                ])
                
                art_prompts_cache[f"{hash(art_prompt)%10000}"] = art_prompt
                
                await callback_query.message.answer_photo(
                    image_url,
                    caption=f"⚡ <b>Похожий арт создан!</b>\n\n🎨 Основа: <i>{description[:100]}...</i>",
                    reply_markup=art_menu,
                    parse_mode="HTML"
                )
                
                # Очищаем кеш
                art_prompts_cache.pop(key, None)
                
            except Exception as e:
                await processing_msg.delete()
                logger.error(f"Ошибка генерации похожего арта: {e}")
                await callback_query.message.answer("❌ Не удалось сгенерировать похожее изображение. Попробуйте позже.")
        else:
            await callback_query.message.answer("❌ Описание изображения не найдено. Попробуйте отправить изображение снова.")
    
    elif callback_query.data.startswith("regenerate_art_"):
        # Повторная генерация арта
        key = callback_query.data.replace("regenerate_art_", "")
        prompt = art_prompts_cache.get(key)
        
        if prompt:
            await generate_art_image(callback_query.message, prompt)
        else:
            await callback_query.message.answer("❌ Промпт не найден. Попробуйте создать новое изображение через /art.")
    
    # 🧠 Обработчики для персонального ассистента
    elif callback_query.data == "pa_add_memory":
        await callback_query.message.answer(
            "🧠 <b>Добавить память</b>\n\n"
            "📝 Напишите что-то, что вы хотите, чтобы я запомнил о вас:\n\n"
            "💡 <i>Примеры:</i>\n"
            "• Мне нравится стиль минимализм\n"
            "• Я работаю программистом\n"
            "• Предпочитаю краткие ответы\n"
            "• Я изучаю Python",
            parse_mode="HTML"
        )
        # Переключаем пользователя в режим добавления памяти
        # Будем обрабатывать следующее сообщение как память
        user_states[callback_query.from_user.id] = "adding_memory"
    
    elif callback_query.data == "pa_view_stats":
        # Показываем статистику памяти пользователя
        await show_personal_memory_stats(callback_query.message, callback_query.from_user.id)
    
    elif callback_query.data == "pa_clear_memory":
        # Подтверждение очистки памяти
        confirm_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, очистить всё", callback_data="pa_confirm_clear")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="personal_assistant")]
        ])
        await callback_query.message.answer(
            "⚠️ <b>Внимание!</b>\n\n"
            "Вы уверены, что хотите удалить всю персональную память?\n"
            "Это действие необратимо.",
            reply_markup=confirm_menu,
            parse_mode="HTML"
        )
    
    elif callback_query.data == "pa_confirm_clear":
        # Очищаем память пользователя
        await personal_assistant.clear_user_memory(callback_query.from_user.id)
        await callback_query.message.answer(
            "🗑️ <b>Память очищена</b>\n\n"
            "Вся ваша персональная память была удалена.",
            parse_mode="HTML"
        )
        # Возвращаемся в главное меню
        if is_admin(callback_query.from_user.id):
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=admin_menu)
        else:
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=main_menu)
    
    elif callback_query.data == "pa_toggle_mode":
        # Переключаем режим персонального ассистента
        await toggle_personal_assistant_mode(callback_query.message, callback_query.from_user.id)
    
    elif callback_query.data == "back_to_pa":
        # Возвращаемся в меню персонального ассистента
        await show_personal_assistant_menu(callback_query.message, callback_query.from_user.id)


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
async def handle_image_message(message: types.Message) -> None:
    """Улучшенный обработчик сообщений с изображениями."""
    global pool
    
    # Проверяем, активен ли бот
    if not await is_bot_active(pool):
        await message.answer("⛔ Бот временно отключён администратором.")
        return
    
    # Показываем индикатор "печатает"
    await bot.send_chat_action(message.chat.id, "typing")
    processing_msg = await message.answer("👀 Анализирую изображение...")
    
    try:
        # Получаем самое большое изображение
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        file_path = file_info.file_path
        file_url = f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}"
        
        # Получаем текст сообщения
        caption = message.caption or "Опиши что изображено на этой картинке подробно"
        
        # Скачиваем изображение
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Не удалось скачать: {resp.status}")
                image_data = await resp.read()
        
        # Анализируем через OpenAI Vision
        try:
            response = await openai_vision(image_data, caption)
        except Exception as e:
            logger.error(f"Ошибка анализа: {e}")
            response = "❌ Не удалось проанализировать изображение."
        
        # Усечение длинных ответов
        if len(response) > settings.MAX_TG_REPLY:
            response = response[:settings.MAX_TG_REPLY] + "... (ответ усечён)"
        
        await processing_msg.delete()
        
        # Кнопки для дополнительных действий
        image_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Сгенерировать похожий арт", callback_data=f"generate_similar_{hash(response)%10000}")],
            [InlineKeyboardButton(text="🔄 Сбросить диалог", callback_data="reset_context")]
        ])
        
        # Сохраняем описание
        art_prompts_cache[f"{hash(response)%10000}"] = response
        
        await message.answer(
            f"👀 <b>Анализ изображения:</b>\n\n{response}",
            reply_markup=image_menu,
            parse_mode="HTML"
        )
        
        # Записываем в базу
        if pool:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                        message.from_user.username, "vision", caption, response
                    )
                    await conn.execute(
                        "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                        message.from_user.id, "user", f"[Изображение] {caption}"
                    )
                    await conn.execute(
                        "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                        message.from_user.id, "assistant", response
                    )
            except Exception as e:
                logger.error(f"Ошибка записи в БД: {e}")
    
    except Exception as e:
        await processing_msg.delete()
        logger.error(f"Ошибка анализа изображения: {e}")
        await message.answer("❌ Произошла ошибка при анализе изображения.")


async def generate_art_image(message: types.Message, text: str, size: str = "1024x1024") -> None:
    """Генерирует изображение с указанным размером."""
    try:
        # Показываем индикатор обработки
        await bot.send_chat_action(message.chat.id, "upload_photo")
        processing_msg = await message.answer(f"🎨 Генерирую изображение {size}...")
        
        # Генерируем изображение
        image_url = await openai_image(text, size=size)
        
        # Удаляем сообщение об обработке
        await processing_msg.delete()
        
        # Кнопки для дополнительных действий
        art_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Генерировать ещё", callback_data=f"regenerate_art_{hash(text)%10000}")],
            [InlineKeyboardButton(text="🔄 Сбросить диалог", callback_data="reset_context")]
        ])
        
        # Сохраняем промпт для повторной генерации
        art_prompts_cache[f"{hash(text)%10000}"] = text
        
        # Отправляем изображение
        await message.answer_photo(
            image_url, 
            caption=f"✨ <b>Арт готов!</b>\n\n🎨 Описание: <i>{text}</i>\n📱 Размер: {size}",
            reply_markup=art_menu,
            parse_mode="HTML"
        )
        
        # Записываем в базу
        if pool:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                        message.from_user.username,
                        "art",
                        f"{text} ({size})",
                        f"Сгенерировано: {image_url}",
                    )
            except Exception as e:
                logger.error(f"Ошибка записи в БД: {e}")
                
    except Exception as e:
        if 'processing_msg' in locals():
            await processing_msg.delete()
        logger.error(f"Ошибка генерации изображения: {e}")
        await message.answer("❌ Произошла ошибка при генерации изображения. Попробуйте упростить описание.")


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


@dp.message(Command("personal"))
async def cmd_personal(message: types.Message) -> None:
    """Обработчик команды /personal для быстрого доступа к персональному ассистенту."""
    await show_personal_assistant_menu(message, message.from_user.id)


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
    """Улучшенный обработчик голосовых сообщений с индикатором обработки."""
    global pool
    
    # Проверяем, активен ли бот
    if not await is_bot_active(pool):
        await message.answer("⛔ Бот временно отключён администратором.")
        return
    
    # Показываем индикатор "печатает"
    await bot.send_chat_action(message.chat.id, "typing")
    processing_msg = await message.answer("⚙️ Обрабатываю голосовое сообщение...")
    
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
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status == 200:
                        with open(temp_filename, 'wb') as f:
                            f.write(await response.read())
                    else:
                        raise Exception(f"Не удалось скачать голосовое сообщение: {response.status}")
        except Exception as e:
            await processing_msg.delete()
            logger.error(f"Ошибка скачивания голосового файла: {e}")
            await message.answer("❌ Не удалось скачать голосовое сообщение. Попробуйте ещё раз.")
            return
        
        # Распознаем речь с помощью OpenAI Whisper
        try:
            await bot.send_chat_action(message.chat.id, "typing")
            recognized_text = await openai_stt(temp_filename)
            
            if not recognized_text or len(recognized_text.strip()) == 0:
                raise Exception("Пустой результат распознавания")
                
        except Exception as e:
            await processing_msg.delete()
            logger.error(f"Ошибка распознавания речи: {e}")
            # Удаляем временный файл
            try:
                os.unlink(temp_filename)
            except Exception:
                pass
            await message.answer("❌ Не удалось распознать голосовое сообщение. Проверьте качество записи или попробуйте снова.")
            return
        
        # Удаляем временный файл
        try:
            os.unlink(temp_filename)
        except Exception:
            pass
        
        # Удаляем сообщение об обработке
        await processing_msg.delete()
        
        # Отправляем пользователю распознанный текст и кнопки выбора ответа
        voice_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔊 Ответить голосом", callback_data=f"voice_response_{message.from_user.id}_{hash(recognized_text)%10000}")],
            [InlineKeyboardButton(text="📝 Текстовый ответ", callback_data=f"text_response_{message.from_user.id}_{hash(recognized_text)%10000}")],
            [InlineKeyboardButton(text="🔄 Сбросить диалог", callback_data="reset_context")]
        ])
        
        # Сохраняем распознанный текст в кеше
        cache_key = f"{message.from_user.id}_{hash(recognized_text)%10000}"
        voice_messages_cache[cache_key] = recognized_text
        
        await message.answer(
            f"🎤 <b>Распознано:</b>\n\n<i>{recognized_text}</i>\n\n🤔 Как ответить?",
            reply_markup=voice_menu,
            parse_mode="HTML"
        )
        
    except Exception as e:
        await processing_msg.delete()
        logger.error(f"Общая ошибка при обработке голосового сообщения: {e}")
        await message.answer("❌ Произошла ошибка при обработке голосового сообщения. Попробуйте ещё раз.")


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
        try:
            response = await openai_vision(image_data, caption)
        except Exception as e:
            logger.error(f"Ошибка анализа изображения: {e}")
            response = "❌ Извините, не удалось проанализировать изображение. Попробуйте отправить другое изображение или опишите что на нём текстом."
        
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


async def process_voice_text_message(callback_query: types.CallbackQuery, text: str, voice_response: bool = False) -> None:
    """Обрабатывает распознанный текст из голосового сообщения."""
    global pool
    
    # Проверяем, активен ли бот
    if not await is_bot_active(pool):
        await callback_query.message.answer("⛔ Бот временно отключён администратором.")
        return
    
    text_lower = text.lower()
    
    # Обрабатываем автоматическую генерацию изображений
    image_keywords = ["картинку", "изображение", "нарисуй", "арт", "картина", "рисунок", "фото", "изобрази"]
    if any(word in text_lower for word in image_keywords):
        try:
            image_url = await openai_image(text)
            await callback_query.message.answer_photo(image_url, caption=f"✨ Вот что получилось!")
            
            # Записываем в базу
            if pool:
                try:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                            callback_query.from_user.username,
                            "voice_art",
                            text,
                            f"Сгенерировано изображение из голосового: {image_url}",
                        )
                except Exception as e:
                    logger.error(f"Ошибка при записи в базу данных: {e}")
            return
        except Exception as e:
            logger.error(f"Ошибка при генерации изображения: {e}")
            await callback_query.message.answer("❌ Извините, произошла ошибка при генерации изображения.")
            return
    
    try:
        # Получаем модель пользователя
        user_model = None
        if pool:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT preferred_model FROM user_settings WHERE user_id = $1",
                        callback_query.from_user.id
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
                        callback_query.from_user.id
                    )
                    dialog_history = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
            except Exception as e:
                logger.error(f"Ошибка при получении истории диалога: {e}")
        
        # Добавляем текущее сообщение
        dialog_history.append({"role": "user", "content": text})
        
        # Получаем ответ от OpenAI
        try:
            response = await openai_chat_with_history(DEFAULT_SYSTEM_PROMPT, dialog_history, user_model)
        except Exception as e:
            logger.error(f"Ошибка OpenAI API: {e}")
            response = "❌ Извините, сейчас проблемы с AI сервисом. Попробуйте позже."
        
        # Ограничиваем длину
        if len(response) > settings.MAX_TG_REPLY:
            response = response[:settings.MAX_TG_REPLY] + "... (ответ усечён)"
        
        # Отправляем ответ (голосовой или текстовый)
        if voice_response and len(response) < 4000:  # Ограничение для TTS
            try:
                # Получаем настройки голоса
                tts_voice = "alloy"
                if pool:
                    try:
                        async with pool.acquire() as conn:
                            row = await conn.fetchrow(
                                "SELECT tts_voice FROM user_settings WHERE user_id = $1",
                                callback_query.from_user.id
                            )
                            if row:
                                tts_voice = row["tts_voice"]
                    except Exception as e:
                        logger.error(f"Ошибка при получении настроек TTS: {e}")
                
                # Генерируем голосовое сообщение
                audio_content = await openai_tts(response, tts_voice)
                
                # Создаем временный файл
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                    temp_filename = temp_file.name
                    temp_file.write(audio_content)
                
                # Отправляем голосовое сообщение
                from aiogram.types import FSInputFile
                audio = FSInputFile(temp_filename, filename="response.mp3")
                caption = response[:1000] + "..." if len(response) > 1000 else response
                await callback_query.message.answer_voice(audio, caption=caption)
                
                # Удаляем временный файл
                os.unlink(temp_filename)
            except Exception as e:
                logger.error(f"Ошибка при генерации голосового ответа: {e}")
                # Отправляем текстовый ответ в случае ошибки
                await callback_query.message.answer(response)
        else:
            # Отправляем текстовый ответ
            await callback_query.message.answer(response)
        
        # Записываем в базу
        if pool:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                        callback_query.from_user.username,
                        "voice_message",
                        text,
                        response,
                    )
                    # Сохраняем в истории диалога
                    await conn.execute(
                        "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                        callback_query.from_user.id, "user", text
                    )
                    await conn.execute(
                        "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                        callback_query.from_user.id, "assistant", response
                    )
            except Exception as e:
                logger.error(f"Ошибка при записи в базу данных: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка обработки голосового сообщения: {e}")
        await callback_query.message.answer("❌ Извините, произошла ошибка при обработке вашего сообщения.")


async def process_text_message(message) -> None:
    """Обрабатывает текстовое сообщение (обычное или из голосового)."""
    global pool
    
    # Игнорируем сообщения без текста
    if not message.text:
        return
    
    # Проверяем состояние пользователя для персонального ассистента
    user_id = message.from_user.id
    user_state = user_states.get(user_id)
    
    # Если пользователь добавляет память
    if user_state == "adding_memory":
        try:
            await personal_assistant.add_user_memory(
                user_id, 
                message.text, 
                "custom",
                {"category": "user_added"}
            )
            user_states.pop(user_id, None)  # Убираем состояние
            
            await message.answer(
                "✅ <b>Память сохранена!</b>\n\n"
                "🧠 Я запомнил эту информацию и буду учитывать её в будущих ответах.",
                parse_mode="HTML"
            )
            
            # Показываем меню персонального ассистента
            await show_personal_assistant_menu(message, user_id)
            return
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении памяти: {e}")
            user_states.pop(user_id, None)  # Убираем состояние
            await message.answer(
                "❌ Произошла ошибка при сохранении памяти. Попробуйте позже."
            )
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
        
        # Проверяем, включён ли персональный режим
        pa_enabled = await get_personal_assistant_mode(user_id)
        
        # Получаем ответ от OpenAI с учётом истории и персонального контекста
        try:
            if pa_enabled:
                # Получаем персональный контекст для пользователя
                user_context = await personal_assistant.get_user_context(user_id, message.text)
                
                # Используем персональный контекст
                response = await openai_chat_with_personal_context(
                    DEFAULT_SYSTEM_PROMPT, 
                    dialog_history, 
                    user_context,
                    user_model
                )
                
                # Обучаем персонального ассистента на основе диалога
                await personal_assistant.learn_from_dialogue(user_id, message.text, response)
            else:
                # Обычный режим без персонального контекста
                response = await openai_chat_with_history(DEFAULT_SYSTEM_PROMPT, dialog_history, user_model)
        except Exception as e:
            logger.error(f"Ошибка OpenAI API: {e}")
            # Fallback на простой ответ
            response = "❌ Извините, сейчас проблемы с AI сервисом. Попробуйте позже или обратитесь к администратору."
            # Записываем ошибку в логи для мониторинга
            if pool:
                try:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                            message.from_user.username,
                            "error_api",
                            str(e),
                            "❌ OpenAI API недоступен"
                        )
                except Exception:
                    pass  # Игнорируем ошибки логирования
        
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


# 🧠 Функции для персонального ассистента

async def show_personal_assistant_menu(message: types.Message, user_id: int) -> None:
    """Показывает меню персонального ассистента."""
    try:
        # Получаем статистику памяти
        stats = await personal_assistant.get_user_stats(user_id)
        total_memories = stats.get("total_memories", 0)
        
        # Проверяем, включен ли персональный режим
        pa_enabled = await get_personal_assistant_mode(user_id)
        pa_status = "🟢 Включён" if pa_enabled else "🔴 Выключен"
        
        pa_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📊 Статистика ({total_memories})", callback_data="pa_view_stats")],
            [InlineKeyboardButton(text="🧠 Добавить память", callback_data="pa_add_memory")],
            [InlineKeyboardButton(text=f"🎛️ Персональный режим: {pa_status}", callback_data="pa_toggle_mode")],
            [InlineKeyboardButton(text="🗑️ Очистить память", callback_data="pa_clear_memory")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
        ])
        
        await message.answer(
            f"🧠 <b>Персональный ассистент</b>\n\n"
            f"💫 Использует векторную память для персонализации ответов\n\n"
            f"📋 <b>Статус:</b> {pa_status}\n"
            f"📦 <b>Запомнено:</b> {total_memories} записей\n\n"
            f"💡 Когда персональный режим включён, я буду учитывать ваши предпочтения и опыт при ответах.",
            reply_markup=pa_menu,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при отображении меню персонального ассистента: {e}")
        await message.answer("❌ Ошибка при загрузке меню персонального ассистента.")


async def show_personal_memory_stats(message: types.Message, user_id: int) -> None:
    """Показывает статистику памяти пользователя."""
    try:
        stats = await personal_assistant.get_user_stats(user_id)
        total_memories = stats.get("total_memories", 0)
        by_type = stats.get("by_type", {})
        
        stats_text = f"📊 <b>Статистика памяти</b>\n\n"
        stats_text += f"📦 <b>Всего записей:</b> {total_memories}\n\n"
        
        if by_type:
            stats_text += "📊 <b>По типам:</b>\n"
            for memory_type, count in by_type.items():
                type_names = {
                    "dialogue": "💬 Диалоги",
                    "preference": "❤️ Предпочтения",
                    "fact": "📝 Факты",
                    "custom": "🏷️ Пользовательские"
                }
                type_name = type_names.get(memory_type, memory_type.title())
                stats_text += f"• {type_name}: {count}\n"
        else:
            stats_text += "😊 Пока нет сохранённых воспоминаний."
        
        stats_text += "\n\n💡 Добавляйте новые воспоминания, чтобы я лучше вас понимал!"
        
        back_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к меню", callback_data="back_to_pa")]
        ])
        
        await message.answer(stats_text, reply_markup=back_menu, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики памяти: {e}")
        await message.answer("❌ Ошибка при получении статистики.")


async def get_personal_assistant_mode(user_id: int) -> bool:
    """Получает статус персонального режима для пользователя."""
    global pool
    
    if not pool:
        return False
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT personal_assistant_enabled FROM user_settings WHERE user_id = $1",
                user_id
            )
            if row:
                return row["personal_assistant_enabled"] or False
            return False
    except Exception as e:
        logger.error(f"Ошибка при получении статуса персонального ассистента: {e}")
        return False


async def set_personal_assistant_mode(user_id: int, enabled: bool) -> None:
    """Устанавливает режим персонального ассистента."""
    global pool
    
    if not pool:
        return
    
    try:
        async with pool.acquire() as conn:
            # Проверяем, есть ли уже настройки пользователя
            existing = await conn.fetchrow(
                "SELECT user_id FROM user_settings WHERE user_id = $1",
                user_id
            )
            
            if existing:
                # Обновляем существующие настройки
                await conn.execute(
                    "UPDATE user_settings SET personal_assistant_enabled = $1, updated_at = now() WHERE user_id = $2",
                    enabled, user_id
                )
            else:
                # Создаём новые настройки
                await conn.execute(
                    "INSERT INTO user_settings (user_id, personal_assistant_enabled, preferred_model, tts_enabled, tts_voice) VALUES ($1, $2, $3, $4, $5)",
                    user_id, enabled, "gpt-4o", False, "alloy"
                )
    except Exception as e:
        logger.error(f"Ошибка при сохранении режима персонального ассистента: {e}")


async def toggle_personal_assistant_mode(message: types.Message, user_id: int) -> None:
    """Переключает режим персонального ассистента."""
    try:
        current_mode = await get_personal_assistant_mode(user_id)
        new_mode = not current_mode
        await set_personal_assistant_mode(user_id, new_mode)
        
        status = "🟢 включён" if new_mode else "🔴 выключен"
        await message.answer(f"🎛️ Персональный режим {status}!")
        
        # Обновляем меню
        await show_personal_assistant_menu(message, user_id)
        
    except Exception as e:
        logger.error(f"Ошибка при переключении режима персонального ассистента: {e}")
        await message.answer("❌ Ошибка при переключении режима.")


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
            
            # Проверяем статус webhook
            webhook_info = await webhook_manager.get_telegram_webhook_info()
            if webhook_info:
                logger.info(f"📊 Webhook URL: {webhook_info.url}")
                if webhook_info.last_error_date:
                    logger.warning(f"⚠️ Последняя ошибка: {webhook_info.last_error_message}")
            
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
