"""
Основной модуль Telegram‑бота с поддержкой команды /suggest_prompt и логированием.

Этот модуль использует библиотеку aiogram v3 для асинхронной работы с
Telegram‑API, а также асинхронный драйвер asyncpg для записи логов в
PostgreSQL. Он подключается к OpenAI через модуль ai для генерации
ответов на сообщения пользователей.

TODO: Этот файл слишком большой (2300+ строк) и требует рефакторинга.
Планируется разделение на модули handlers/, services/, models/.
"""

import logging
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

from .config import settings
from .constants import (
    SEARCH_KEYWORDS, IMAGE_KEYWORDS, DEFAULT_SYSTEM_PROMPT, 
    ERROR_MESSAGES, MAX_TTS_LENGTH
)
from .services.search_service import search_service
from .suggest import generate_prompt_from_logs
from .ai import openai_chat, openai_image, openai_vision, openai_tts, openai_stt, openai_chat_with_history, openai_chat_with_personal_context
from .admin import is_admin, is_super_admin, cmd_admin_stats, cmd_errors, cmd_bot_on, cmd_bot_off, is_bot_active
from .handlers import route_callback
from .webhook import WebhookManager
from .vector_memory import personal_assistant

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Удалено: Tavily integration - теперь в services/search_service.py
# Удалено: search_web, search_news, format_search_results - теперь в SearchService


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

# Кеш ответов для кнопки "Переформулировать"
response_cache: Dict[str, str] = {}
# Кеш полнотекстовых ответов для кнопки "Показать полностью"
full_response_cache: Dict[str, str] = {}
# Выбранный режим ответа пользователя
user_modes: Dict[int, str] = {}

# Удалено: DEFAULT_SYSTEM_PROMPT перенесен в constants.py

# Словари для локализации
LOCALIZATION = {
    "ru": {
        "welcome": """🌟 ═══════════════════════════ 🌟
⚡ AI Agent ⚡
🌟 ═══════════════════════════ 🌟

🚀 Ваш интеллектуальный помощник готов к работе!

📋 Возможности:
📂 Работа с документами и файлами
🧠 Решение задач разного уровня
😉 Создание контента
💻 Работа с кодом
✍️ Копирайтинг и рерайтинг
🎨 Визуальный контент
🖼️ Генерация изображений
🌍 Перевод и краткий пересказ

💡 Выберите действие из меню ниже:""",
        "main_menu": "🏠 Главное меню",
        "ai_chat": "💬 ИИ Чат",
        "creativity": "🎨 Творчество", 
        "settings": "🔧 Настройки",
        "help": "ℹ️ Помощь",
        "admin_panel": "👑 Админ-панель",
        "ai_agent_pro": "⚡ AI Agent-PRO ⚡",
        "change_language": "🌐 Смена языка 🌐",
        "language_interface": "🌐 Язык интерфейса",
        "select_language": "🌐 Выберите язык:",
        "ai_model": "🤖 Модель ИИ",
        "language_set": "✅ Язык установлен: {lang}",
        "back": "⬅️ Назад",
        "russian": "🇷🇺 Русский",
        "english": "🇺🇸 English",
        "versions_title": "⚡ AI Agent – версии",
        "version_free": "🔹 FREE",
        "version_pro": "🔹 PRO", 
        "version_ultra": "🔹 ULTRA",
        "free_features": "– Базовый функционал (чат, переводы, простые тексты)\n– Ограниченный лимит сообщений\n– Без визуального контента",
        "pro_features": "– Всё из FREE +\n– Работа с файлами и документами\n– Генерация изображений\n– Копирайтинг, рерайтинг, SEO\n– OCR (распознавание текста с картинок)",
        "ultra_features": "– Всё из PRO +\n– Подключение к API (ChatGPT, MidJourney)\n– Визуальный контент без ограничений\n– Командная работа\n– Приоритетная скорость",
        "functionality_title": "📌 Функционал AI Agent:",
        "target_users": "👥 Целевые пользователи:\n\n📚 Студенты (написание дипломов/эссе/курсовых/сочинений/рефератов)\n\n✍️ Копирайтеры (написание на 100% уникальных текстов, рерайт, обход ИИ-детекта, обход \"Антиплагиат\")\n\n📱 Блогеры (создание контент-планов, триггерных заголовков, сторителлинга, сценариев для блога и Reels)\n\n🔍 SEO-специалисты (написание больших статей, парсинг поисковых систем, анализ по ключевым словам)\n\n📸 Распознавание текста с картинки (фотографии) и многое другое! 🚀",
        "web_search": "🔍 Поиск в интернете",
        "search_news": "📰 Поиск новостей",
        "search_results": "🔍 Результаты поиска",
        "search_placeholder": "Введите запрос для поиска...",
        "search_help": "Используйте /search [запрос] для поиска в интернете\n/news [запрос] для поиска новостей"
    },
    "en": {
        "welcome": """🌟 ═══════════════════════════ 🌟
⚡ AI Agent ⚡
🌟 ═══════════════════════════ 🌟

🚀 Your intelligent assistant is ready to work!

📋 Capabilities:
📂 Document and file processing
🧠 Problem solving at different levels
😉 Content creation
💻 Code development
✍️ Copywriting and rewriting
🎨 Visual content
🖼️ Image generation
🌍 Translation and summarization

💡 Choose an action from the menu below:""",
        "main_menu": "🏠 Main Menu", 
        "ai_chat": "💬 AI Chat",
        "creativity": "🎨 Creativity",
        "settings": "🔧 Settings",
        "help": "ℹ️ Help",
        "admin_panel": "👑 Admin Panel",
        "ai_agent_pro": "⚡ AI Agent-PRO ⚡",
        "change_language": "🌐 Change Language 🌐",
        "language_interface": "🌐 Interface Language",
        "select_language": "🌐 Select language:",
        "ai_model": "🤖 AI Model", 
        "language_set": "✅ Language set to: {lang}",
        "back": "⬅️ Back",
        "russian": "🇷🇺 Русский",
        "english": "🇺🇸 English",
        "versions_title": "⚡ AI Agent – versions",
        "version_free": "🔹 FREE",
        "version_pro": "🔹 PRO",
        "version_ultra": "🔹 ULTRA",
        "free_features": "– Basic functionality (chat, translations, simple texts)\n– Limited message quota\n– No visual content",
        "pro_features": "– Everything from FREE +\n– File and document processing\n– Image generation\n– Copywriting, rewriting, SEO\n– OCR (text recognition from images)",
        "ultra_features": "– Everything from PRO +\n– API connections (ChatGPT, MidJourney)\n– Unlimited visual content\n– Team collaboration\n– Priority speed",
        "functionality_title": "📌 AI Agent Functionality:",
        "target_users": "👥 Target Users:\n\n📚 Students (writing theses/essays/coursework/compositions/reports)\n\n✍️ Copywriters (writing 100% unique texts, rewriting, bypassing AI detection, bypassing \"Anti-plagiarism\")\n\n📱 Bloggers (creating content plans, trigger headlines, storytelling, scripts for blogs and Reels)\n\n🔍 SEO specialists (writing large articles, search engine parsing, keyword analysis)\n\n📸 Text recognition from images (photos) and much more! 🚀",
        "web_search": "🔍 Web Search",
        "search_news": "📰 News Search", 
        "search_results": "🔍 Search Results",
        "search_placeholder": "Enter search query...",
        "search_help": "Use /search [query] to search the web\n/news [query] to search for news"
    }
}

def get_text(key: str, language: str = "ru", **kwargs) -> str:
    """Получает локализованный текст."""
    text = LOCALIZATION.get(language, LOCALIZATION["ru"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


def format_answer(language: str, content: str, title: str | None = None) -> str:
    """Унифицированное оформление ответов бота (HTML-верстка)."""
    header = title or ("💬 Ответ" if language == "ru" else "💬 Response")
    # Усечем слишком длинные префиксы пробелов
    body = content.strip()
    # Добавим мягкий каркас
    parts = [
        f"<b>{header}</b>",
        "\n",
        body,
    ]
    return "\n".join(parts)

def get_mode_instruction(user_id: int) -> str:
    """Возвращает инструкцию для выбранного режима пользователя."""
    mode = user_modes.get(user_id)
    if mode == "seo":
        return "\n\nРежим: Эксперт по SEO. Пиши структурировано, с H2/H3, списками, примерами ключевых слов."
    if mode == "lawyer":
        return "\n\nРежим: Юрист. Пиши аккуратно, с оговорками, ссылками на нормы (если известны)."
    if mode == "teacher":
        return "\n\nРежим: Учитель. Объясняй просто, по шагам, с примерами."
    if mode == "code":
        return "\n\nРежим: Редактор кода. Дай пример кода, поясни кратко, укажи шаги."
    return ""

def get_main_menu(user_lang: str = "ru") -> InlineKeyboardMarkup:
    """Создаёт главное меню на соответствующем языке."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text("ai_chat", user_lang), callback_data="ai_chat_menu"),
         InlineKeyboardButton(text=get_text("creativity", user_lang), callback_data="creative_menu")],
        [InlineKeyboardButton(text=get_text("settings", user_lang), callback_data="settings_menu"),
         InlineKeyboardButton(text=get_text("help", user_lang), callback_data="help")],
        [InlineKeyboardButton(text=get_text("ai_agent_pro", user_lang), callback_data="ai_agent_pro")],
    ])


def get_admin_menu(user_lang: str = "ru") -> InlineKeyboardMarkup:
    """Создаёт админское меню на соответствующем языке."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text("ai_chat", user_lang), callback_data="ai_chat_menu"),
         InlineKeyboardButton(text=get_text("creativity", user_lang), callback_data="creative_menu")],
        [InlineKeyboardButton(text=get_text("settings", user_lang), callback_data="settings_menu"),
         InlineKeyboardButton(text=get_text("admin_panel", user_lang), callback_data="admin_panel")],
        [InlineKeyboardButton(text=get_text("ai_agent_pro", user_lang), callback_data="ai_agent_pro")],
        [InlineKeyboardButton(text=get_text("help", user_lang), callback_data="help")],
    ])


WELCOME_TEXT = """
Добро пожаловать, {username}!

🤖 Ваш AI Agent

🚀 Используйте кнопки ниже для доступа к функциям!
"""

# Создание главного меню с категоризацией функций
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💬 ИИ Чат", callback_data="ai_chat_menu"),
     InlineKeyboardButton(text="🎨 Творчество", callback_data="creative_menu")],
    [InlineKeyboardButton(text="🔧 Настройки", callback_data="settings_menu"),
     InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    [InlineKeyboardButton(text="⚡ AI Agent-PRO ⚡", callback_data="ai_agent_pro")],
])

# Расширенное меню для администраторов
admin_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💬 ИИ Чат", callback_data="ai_chat_menu"),
     InlineKeyboardButton(text="🎨 Творчество", callback_data="creative_menu")],
    [InlineKeyboardButton(text="🔧 Настройки", callback_data="settings_menu"),
     InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")],
    [InlineKeyboardButton(text="⚡ AI Agent-PRO ⚡", callback_data="ai_agent_pro")],
    [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
])

# Меню ИИ Чата
ai_chat_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💬 Начать чат", callback_data="start_chat"),
     InlineKeyboardButton(text="🤖 Выбрать модель", callback_data="select_model")],
    [InlineKeyboardButton(text="🔍 Поиск в сети", callback_data="web_search_menu"),
     InlineKeyboardButton(text="📰 Поиск новостей", callback_data="news_search_menu")],
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
     InlineKeyboardButton(text="🌍 Язык интерфейса", callback_data="language_settings")],
    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_to_main")],
])

# Меню админских команд
admin_commands_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Админ статистика", callback_data="admin_stats"),
     InlineKeyboardButton(text="⚠️ Ошибки системы", callback_data="errors")],
    [InlineKeyboardButton(text="✅ Включить бота", callback_data="bot_on"),
     InlineKeyboardButton(text="❌ Выключить бота", callback_data="bot_off")],
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
    # Получаем предпочитаемый язык пользователя
    user_lang = await get_user_language(message.from_user.id)
    
    # Формируем модерное приветствие без персонализации
    welcome_text = get_text("welcome", user_lang)
    
    # Показываем расширенное меню для супер-администратора, обычное для остальных
    if is_super_admin(message.from_user.id):
        await message.answer(welcome_text, reply_markup=get_admin_menu(user_lang))
    else:
        await message.answer(welcome_text, reply_markup=get_main_menu(user_lang))


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
            check_yes = "✅"
            check_no = "❌"
            stats_text += f"🤖 Модель: {user_settings['preferred_model'] or 'gpt-4o'}\n"
            stats_text += f"🔊 TTS: {check_yes if user_settings['tts_enabled'] else check_no}\n"
            stats_text += f"🧠 Личный ассистент: {check_yes if user_settings['personal_assistant_enabled'] else check_no}\n"
        
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
    
    # Используем новый маршрутизатор для новых callback-ов
    if callback_query.data in ["ai_agent_pro", "back_to_main", "change_language", "set_lang_ru", "set_lang_en", "toggle_versions_lang", "show_welcome"]:
        await route_callback(callback_query)
        return
    
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
        user_lang = await get_user_language(callback_query.from_user.id)
        language_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("russian", user_lang), callback_data="set_lang_ru"),
             InlineKeyboardButton(text=get_text("english", user_lang), callback_data="set_lang_en")],
            [InlineKeyboardButton(text=get_text("back", user_lang), callback_data="settings_menu")]
        ])
        menu_text = f"<b>{get_text('language_interface', user_lang)}</b>\n\n{get_text('select_language', user_lang)}"
        await callback_query.message.answer(
            menu_text,
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
        await set_user_language(callback_query.message, callback_query.from_user.id, lang)
        
        # Отображаем подтверждение на выбранном языке
        lang_names = {"ru": "Русский", "en": "English"}
        confirmation_text = get_text("language_set", lang, lang=lang_names.get(lang, lang))
        
        # Обновляем сообщение с главным меню на новом языке
        welcome_text = get_text("welcome", lang)
        
        # Показываем подтверждение + обновлённое меню
        full_text = f"{confirmation_text}\n\n{welcome_text}"
        
        try:
            if is_super_admin(callback_query.from_user.id):
                await callback_query.message.edit_text(full_text, reply_markup=get_admin_menu(lang))
            else:
                await callback_query.message.edit_text(full_text, reply_markup=get_main_menu(lang))
        except Exception as e:
            # Если редактирование не удалось
            await callback_query.message.answer(confirmation_text)
            if is_super_admin(callback_query.from_user.id):
                await callback_query.message.answer(welcome_text, reply_markup=get_admin_menu(lang))
            else:
                await callback_query.message.answer(welcome_text, reply_markup=get_main_menu(lang))
    elif callback_query.data == "reset_context":
        # Вызываем команду сброса контекста
        await cmd_reset_context(callback_query.message)
        # Возвращаемся в главное меню
        if is_super_admin(callback_query.from_user.id):
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=admin_menu)
        else:
            await callback_query.message.answer("🏠 <b>Главное меню</b>", reply_markup=main_menu)
    elif callback_query.data == "ai_agent_pro":
        user_lang = await get_user_language(callback_query.from_user.id)
        
        # Создаём карточку с версиями AI Agent
        versions_text = f"<b>{get_text('versions_title', user_lang)}</b>\n\n"
        
        # Версия FREE
        versions_text += f"{get_text('version_free', user_lang)}\n"
        versions_text += f"{get_text('free_features', user_lang)}\n\n"
        
        # Версия PRO  
        versions_text += f"{get_text('version_pro', user_lang)}\n"
        versions_text += f"{get_text('pro_features', user_lang)}\n\n"
        
        # Версия ULTRA
        versions_text += f"{get_text('version_ultra', user_lang)}\n"
        versions_text += f"{get_text('ultra_features', user_lang)}\n\n"
        
        # Разделитель
        versions_text += "───\n\n"
        
        # Функционал AI Agent
        versions_text += f"{get_text('functionality_title', user_lang)}\n\n"
        versions_text += f"{get_text('target_users', user_lang)}"
        
        pro_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("back", user_lang), callback_data="back_to_main")]
        ])
        
        # Используем edit_message_text вместо нового сообщения
        try:
            await callback_query.message.edit_text(
                versions_text,
                reply_markup=pro_menu,
                parse_mode="HTML"
            )
        except Exception as e:
            # Если редактирование не удалось, отправляем новое сообщение
            await callback_query.message.answer(
                versions_text,
                reply_markup=pro_menu,
                parse_mode="HTML"
            )
    elif callback_query.data == "change_language":
        user_lang = await get_user_language(callback_query.from_user.id)
        
        language_menu = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text("russian", user_lang), callback_data="set_lang_ru"),
             InlineKeyboardButton(text=get_text("english", user_lang), callback_data="set_lang_en")],
            [InlineKeyboardButton(text=get_text("back", user_lang), callback_data="back_to_main")]
        ])
        
        menu_text = f"<b>{get_text('language_interface', user_lang)}</b>\n\n{get_text('select_language', user_lang)}"
        
        # Используем edit_message_text
        try:
            await callback_query.message.edit_text(
                menu_text,
                reply_markup=language_menu,
                parse_mode="HTML"
            )
        except Exception as e:
            await callback_query.message.answer(
                menu_text,
                reply_markup=language_menu,
                parse_mode="HTML"
            )
    elif callback_query.data == "help":
        # Отображаем упрощённую справку
        help_text = (
            "ℹ️ <b>Интерфейс бота:</b>\n\n"
            "📋 <b>Основные разделы:</b>\n"
            "💬 ИИ Чат - Общение с ИИ\n"
            "🔧 Настройки - Персонализация\n\n"
            "🚀 <b>Начните с /start</b> для возвращения в главное меню!"
        )
        
        await callback_query.message.answer(help_text, parse_mode="HTML")
        # Отображаем упрощённую справку
        help_text = (
            "ℹ️ <b>Интерфейс бота:</b>\n\n"
            "📋 <b>Основные разделы:</b>\n"
            "💬 ИИ Чат - Общение с ИИ\n"
            "🎨 Творчество - Создание изображений\n"
            "🔧 Настройки - Персонализация\n\n"
            "🚀 <b>Начните с /start</b> для возвращения в главное меню!"
        )
        
        await callback_query.message.answer(help_text, parse_mode="HTML")
    elif callback_query.data == "admin_panel":
        # Проверяем, является ли пользователь супер-администратором с расширенным логированием
        user_id = callback_query.from_user.id
        admins_raw = os.getenv("ADMINS", "")
        logger.info(f"👑 ДИАГНОСТИКА СУПЕР-АДМИН ДОСТУПА:")
        logger.info(f"   user_id={user_id} (тип: {type(user_id)})")
        logger.info(f"   ADMINS env={repr(admins_raw)}")
        logger.info(f"   ADMINS parsed={settings.ADMINS}")
        logger.info(f"   is_admin result={is_admin(user_id)}")
        logger.info(f"   is_super_admin result={is_super_admin(user_id)}")
        
        if is_super_admin(user_id):
            logger.info(f"✅ Супер-админский доступ РАЗРЕШЁН для user_id={user_id}")
            await callback_query.message.answer("👑 <b>Админ-панель</b>", reply_markup=admin_commands_menu)
        else:
            logger.warning(f"❌ Супер-админский доступ ЗАПРЕЩЁН для user_id={user_id}")
            logger.warning(f"💡 Админ-панель доступна только основному администратору")
            await callback_query.message.answer(
                f"⛔ У вас нет доступа к админ-панели.\n\n"
                f"📝 Ваш ID: {user_id}\n\n"
                f"💡 Админ-панель доступна только основному администратору."
            )
    elif callback_query.data == "web_search_menu":
        # Меню поиска в сети
        await callback_query.message.answer(
            "🔍 <b>Поиск в сети</b>\n\n"
            "Используйте /search [запрос] для поиска актуальной информации в интернете.\n\n"
            "📝 <b>Пример:</b>\n"
            "/search погода в Москве\n"
            "/search курс доллара сегодня",
            parse_mode="HTML"
        )
    elif callback_query.data == "news_search_menu":
        # Меню поиска новостей
        await callback_query.message.answer(
            "📰 <b>Поиск новостей</b>\n\n"
            "Используйте /news [запрос] для поиска последних новостей.\n\n"
            "📝 <b>Примеры:</b>\n"
            "/news технологии\n"
            "/news экономика России\n"
            "/news (без параметров) - общие новости",
            parse_mode="HTML"
        )
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
        user_id = callback_query.from_user.id
        logger.info(f"🔍 ПРОВЕРКА ДОСТУПА К admin_stats:")
        logger.info(f"   user_id={user_id} (тип: {type(user_id)})")
        logger.info(f"   is_admin result={is_admin(user_id)}")
        if is_admin(callback_query.from_user.id):
            logger.info(f"✅ Доступ к admin_stats РАЗРЕШЁН для user_id={user_id}")
            await cmd_admin_stats(callback_query.message, pool)
        else:
            logger.warning(f"❌ Доступ к admin_stats ЗАПРЕЩЁН для user_id={user_id}")
            await callback_query.message.answer("⛔ У вас нет доступа к этой команде.")
    elif callback_query.data == "errors":
        user_id = callback_query.from_user.id
        logger.info(f"🔍 ПРОВЕРКА ДОСТУПА К errors:")
        logger.info(f"   user_id={user_id} (тип: {type(user_id)})")
        logger.info(f"   is_admin result={is_admin(user_id)}")
        if is_admin(callback_query.from_user.id):
            logger.info(f"✅ Доступ к errors РАЗРЕШЁН для user_id={user_id}")
            await cmd_errors(callback_query.message, pool)
        else:
            logger.warning(f"❌ Доступ к errors ЗАПРЕЩЁН для user_id={user_id}")
            await callback_query.message.answer("⛔ У вас нет доступа к этой команде.")
    elif callback_query.data == "bot_on":
        user_id = callback_query.from_user.id
        logger.info(f"🔍 ПРОВЕРКА ДОСТУПА К bot_on:")
        logger.info(f"   user_id={user_id} (тип: {type(user_id)})")
        logger.info(f"   is_admin result={is_admin(user_id)}")
        if is_admin(callback_query.from_user.id):
            logger.info(f"✅ Доступ к bot_on РАЗРЕШЁН для user_id={user_id}")
            await cmd_bot_on(callback_query.message, pool)
        else:
            logger.warning(f"❌ Доступ к bot_on ЗАПРЕЩЁН для user_id={user_id}")
            await callback_query.message.answer("⛔ У вас нет доступа к этой команде.")
    elif callback_query.data == "bot_off":
        user_id = callback_query.from_user.id
        logger.info(f"🔍 ПРОВЕРКА ДОСТУПА К bot_off:")
        logger.info(f"   user_id={user_id} (тип: {type(user_id)})")
        logger.info(f"   is_admin result={is_admin(user_id)}")
        if is_admin(callback_query.from_user.id):
            logger.info(f"✅ Доступ к bot_off РАЗРЕШЁН для user_id={user_id}")
            await cmd_bot_off(callback_query.message, pool)
        else:
            logger.warning(f"❌ Доступ к bot_off ЗАПРЕЩЁН для user_id={user_id}")
            await callback_query.message.answer("⛔ У вас нет доступа к этой команде.")
    elif callback_query.data == "back_to_main":
        # Возвращаемся в главное меню с редактированием сообщения
        user_lang = await get_user_language(callback_query.from_user.id)
        welcome_text = get_text("welcome", user_lang)
        
        try:
            if is_super_admin(callback_query.from_user.id):
                await callback_query.message.edit_text(welcome_text, reply_markup=get_admin_menu(user_lang))
            else:
                await callback_query.message.edit_text(welcome_text, reply_markup=get_main_menu(user_lang))
        except Exception as e:
            # Если редактирование не удалось
            if is_super_admin(callback_query.from_user.id):
                await callback_query.message.answer(welcome_text, reply_markup=get_admin_menu(user_lang))
            else:
                await callback_query.message.answer(welcome_text, reply_markup=get_main_menu(user_lang))
    elif callback_query.data == "back_to_settings":
        # Не нужно, так как settings_menu убрано
        if is_super_admin(callback_query.from_user.id):
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
    elif callback_query.data.startswith("rephrase_"):
        # Переформулировать последний ответ
        key = callback_query.data.replace("rephrase_", "")
        original = response_cache.get(key)
        if not original:
            await callback_query.message.answer("❌ Нет текста для переформулирования. Попробуйте снова задать вопрос.")
        else:
            try:
                prompt = "Переформулируй текст короче и проще:" if (await get_user_language(callback_query.from_user.id)) == "ru" else "Rephrase the text shorter and simpler:"
                messages = [
                    {"role": "user", "content": f"{prompt}\n\n{original}"}
                ]
                new_text = await openai_chat_with_history(DEFAULT_SYSTEM_PROMPT, messages, None)
                user_lang_cb = await get_user_language(callback_query.from_user.id)
                # Новая кнопка для цепочки перефраза
                new_key = f"{callback_query.from_user.id}_{hash(new_text)%1000000}"
                response_cache[new_key] = new_text
                rephrase_label = "🔁 Переформулировать" if user_lang_cb == "ru" else "🔁 Rephrase"
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=rephrase_label, callback_data=f"rephrase_{new_key}")]])
                await callback_query.message.answer(format_answer(user_lang_cb, new_text), reply_markup=kb, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка переформулирования: {e}")
                await callback_query.message.answer("❌ Не удалось переформулировать. Попробуйте ещё раз позже.")
    elif callback_query.data.startswith("show_full_"):
        key = callback_query.data.replace("show_full_", "")
        full = full_response_cache.get(key)
        if not full:
            await callback_query.message.answer("❌ Полный текст недоступен.")
        else:
            user_lang_cb = await get_user_language(callback_query.from_user.id)
            rephrase_label = "🔁 Переформулировать" if user_lang_cb == "ru" else "🔁 Rephrase"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=rephrase_label, callback_data=f"rephrase_{key}")]])
            await callback_query.message.answer(format_answer(user_lang_cb, full), reply_markup=kb, parse_mode="HTML")
    elif callback_query.data.startswith("edit_simplify_") or callback_query.data.startswith("edit_examples_"):
        is_simplify = callback_query.data.startswith("edit_simplify_")
        key = callback_query.data.split("_", 2)[-1]
        original = full_response_cache.get(key) or response_cache.get(key)
        if not original:
            await callback_query.message.answer("❌ Текст недоступен.")
        else:
            try:
                lang = await get_user_language(callback_query.from_user.id)
                if is_simplify:
                    instruction = "Сократи и упростись до 5 пунктов, чётко и ясно." if lang == "ru" else "Shorten and simplify into 5 bullet points, clear and concise."
                else:
                    instruction = "Добавь 2-3 практических примера к тексту." if lang == "ru" else "Add 2-3 practical examples to the text."
                messages = [{"role": "user", "content": f"{instruction}\n\n{original}"}]
                edited = await openai_chat_with_history(DEFAULT_SYSTEM_PROMPT, messages, None)
                new_key = f"{callback_query.from_user.id}_{hash(edited)%1000000}"
                full_response_cache[new_key] = edited
                response_cache[new_key] = edited
                rephrase_label = "🔁 Переформулировать" if lang == "ru" else "🔁 Rephrase"
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=rephrase_label, callback_data=f"rephrase_{new_key}")]])
                await callback_query.message.answer(format_answer(lang, edited), reply_markup=kb, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка смарт-редактуры: {e}")
                await callback_query.message.answer("❌ Не удалось отредактировать. Попробуйте позже.")
    elif callback_query.data.startswith("set_model_"):
        # Устанавливаем модель ИИ
        model = callback_query.data.replace("set_model_", "")
        await set_user_model(callback_query.message, model)
        await callback_query.message.answer(f"✅ Модель ИИ успешно изменена на {model}!")
        # Возвращаемся в главное меню
        if is_super_admin(callback_query.from_user.id):
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
        if is_super_admin(callback_query.from_user.id):
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
async def cmd_reset_context_handler(message: types.Message) -> None:
    """Обработчик команды /reset_context."""
    await cmd_reset_context(message)


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


@dp.message(Command("search"))
async def cmd_search(message: types.Message, command: CommandObject) -> None:
    """Обработчик команды /search для поиска в интернете."""
    query = command.args if command.args else None
    
    if not query:
        user_lang = await get_user_language(message.from_user.id)
        help_text = get_text("search_help", user_lang)
        await message.answer(f"ℹ️ {help_text}")
        return
    
    # Показываем индикатор печати
    await bot.send_chat_action(message.chat.id, "typing")
    processing_msg = await message.answer("🔍 Выполняю поиск в интернете...")
    
    try:
        # Выполняем поиск
        results = await search_service.search_web(query, max_results=5)
        
        # Удаляем сообщение о поиске
        await processing_msg.delete()
        
        # Отправляем результаты
        await message.answer(results, parse_mode="Markdown", disable_web_page_preview=True)
        
        # Записываем в базу данных
        if pool:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                        message.from_user.username,
                        "search",
                        query,
                        f"Поиск выполнен: {query[:100]}..."
                    )
            except Exception as e:
                logger.error(f"Ошибка записи поиска в БД: {e}")
        
    except Exception as e:
        await processing_msg.delete()
        logger.error(f"Ошибка поиска: {e}")
        await message.answer("❌ Произошла ошибка при выполнении поиска. Попробуйте позже.")


@dp.message(Command("news"))
async def cmd_news(message: types.Message, command: CommandObject) -> None:
    """Обработчик команды /news для поиска новостей."""
    query = command.args if command.args else "последние новости"
    
    # Показываем индикатор печати
    await bot.send_chat_action(message.chat.id, "typing")
    processing_msg = await message.answer("📰 Ищу последние новости...")
    
    try:
        # Выполняем поиск новостей
        results = await search_service.search_news(query, max_results=3)
        
        # Удаляем сообщение о поиске
        await processing_msg.delete()
        
        # Отправляем результаты
        await message.answer(results, parse_mode="Markdown", disable_web_page_preview=True)
        
        # Записываем в базу данных
        if pool:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                        message.from_user.username,
                        "news",
                        query,
                        f"Поиск новостей: {query[:100]}..."
                    )
            except Exception as e:
                logger.error(f"Ошибка записи новостей в БД: {e}")
        
    except Exception as e:
        await processing_msg.delete()
        logger.error(f"Ошибка поиска новостей: {e}")
        await message.answer("❌ Произошла ошибка при поиске новостей. Попробуйте позже.")


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


async def set_user_language(message: types.Message, user_id: int, language: str) -> None:
    """Устанавливает предпочитаемый язык интерфейса для пользователя."""
    global pool
    
    if not pool:
        await message.answer("❌ База данных недоступна. Настройки не могут быть сохранены.")
        return
    
    try:
        async with pool.acquire() as conn:
            # Проверяем, нет ли колонки language, если нет - добавляем
            try:
                await conn.execute(
                    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'ru'"
                )
            except Exception as e:
                logger.debug(f"Колонка language уже существует или ошибка: {e}")
            
            # Проверяем, есть ли уже настройки пользователя
            existing = await conn.fetchrow(
                "SELECT user_id FROM user_settings WHERE user_id = $1",
                user_id
            )
            
            if existing:
                # Обновляем существующие настройки
                await conn.execute(
                    "UPDATE user_settings SET language = $1, updated_at = now() WHERE user_id = $2",
                    language, user_id
                )
            else:
                # Создаем новые настройки с всеми полями по умолчанию
                await conn.execute(
                    "INSERT INTO user_settings (user_id, language, preferred_model, tts_enabled, tts_voice, personal_assistant_enabled) VALUES ($1, $2, $3, $4, $5, $6)",
                    user_id, language, "gpt-4o", False, "alloy", False
                )
        
        logger.info(f"Пользователь {user_id} изменил язык на {language}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении языка пользователя: {e}")
        await message.answer("❌ Произошла ошибка при сохранении настроек. Попробуйте позже.")


async def get_user_language(user_id: int) -> str:
    """Получает предпочитаемый язык пользователя."""
    global pool
    
    if not pool:
        return "ru"  # Язык по умолчанию
    
    try:
        async with pool.acquire() as conn:
            # Проверяем, существует ли колонка language
            try:
                row = await conn.fetchrow(
                    "SELECT language FROM user_settings WHERE user_id = $1",
                    user_id
                )
                if row and row["language"]:
                    return row["language"]
            except Exception:
                # Колонка language еще не существует
                pass
    except Exception as e:
        logger.error(f"Ошибка при получении языка пользователя: {e}")
    
    return "ru"  # Язык по умолчанию


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
                    "INSERT INTO user_settings (user_id, preferred_model, tts_enabled, tts_voice, language) VALUES ($1, $2, $3, $4, $5)",
                    message.from_user.id, model, False, "alloy", "ru"
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
    
    # Обрабатываем автоматический поиск
    if search_service.detect_search_intent(text, SEARCH_KEYWORDS):
        try:
            # Показываем индикатор поиска
            await bot.send_chat_action(callback_query.message.chat.id, "typing")
            search_msg = await callback_query.message.answer("🔍 Поиск актуальной информации...")
            
            # Выполняем поиск
            search_results = await search_service.search_web(text, max_results=3)
            
            # Отправляем результаты поиска
            await search_msg.delete()
            await callback_query.message.answer(search_results, parse_mode="Markdown", disable_web_page_preview=True)
            
            # Записываем в базу данных
            if pool:
                try:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                            callback_query.from_user.username,
                            "auto_search",
                            text,
                            f"Автоматический поиск: {text[:100]}...",
                        )
                        # Сохраняем сообщение в истории диалога
                        await conn.execute(
                            "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                            callback_query.from_user.id, "user", text
                        )
                        await conn.execute(
                            "INSERT INTO dialog_history (user_id, role, content) VALUES ($1, $2, $3)",
                            callback_query.from_user.id, "assistant", search_results
                        )
                except Exception as e:
                    logger.error(f"Ошибка при записи авто-поиска в БД: {e}")
            return
        except Exception as e:
            logger.error(f"Ошибка автоматического поиска: {e}")
            # Продолжаем с обычным ответом AI
    
    text_lower = text.lower()
    
    # Обрабатываем автоматическую генерацию изображений
    if any(word in text_lower for word in IMAGE_KEYWORDS):
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
            system_prompt = DEFAULT_SYSTEM_PROMPT + get_mode_instruction(callback_query.from_user.id)
            response = await openai_chat_with_history(system_prompt, dialog_history, user_model)
        except Exception as e:
            logger.error(f"Ошибка OpenAI API: {e}")
            response = "❌ Извините, сейчас проблемы с AI сервисом. Попробуйте позже."
        
        # Ограничиваем длину
        if len(response) > settings.MAX_TG_REPLY:
            response = response[:settings.MAX_TG_REPLY] + "... (ответ усечён)"
        
        # Отправляем ответ (голосовой или текстовый) с оформлением
        if voice_response and len(response) < MAX_TTS_LENGTH:  # Ограничение для TTS
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
                await callback_query.message.answer(format_answer("ru", response), parse_mode="HTML")
        else:
            # Отправляем текстовый ответ
            user_lang_cb = await get_user_language(callback_query.from_user.id)
            # Кешируем полный ответ
            full_key = f"{callback_query.from_user.id}_{hash(response)%1000000}"
            full_response_cache[full_key] = response
            response_cache[full_key] = response
            # Если длинный — показать превью + кнопка "Показать полностью"
            preview_limit = 800
            if len(response) > preview_limit:
                preview = response[:preview_limit] + "…"
                buttons = [
                    [InlineKeyboardButton(text=("🔎 Показать полностью" if user_lang_cb == "ru" else "🔎 Show full"), callback_data=f"show_full_{full_key}")],
                    [InlineKeyboardButton(text=("🔁 Переформулировать" if user_lang_cb == "ru" else "🔁 Rephrase"), callback_data=f"rephrase_{full_key}")],
                    [InlineKeyboardButton(text=("✨ Упростить" if user_lang_cb == "ru" else "✨ Simplify"), callback_data=f"edit_simplify_{full_key}"),
                     InlineKeyboardButton(text=("📌 Примеры" if user_lang_cb == "ru" else "📌 Examples"), callback_data=f"edit_examples_{full_key}")]
                ]
                kb = InlineKeyboardMarkup(inline_keyboard=buttons)
                await callback_query.message.answer(format_answer(user_lang_cb, preview), reply_markup=kb, parse_mode="HTML")
            else:
                buttons = [
                    [InlineKeyboardButton(text=("🔁 Переформулировать" if user_lang_cb == "ru" else "🔁 Rephrase"), callback_data=f"rephrase_{full_key}")],
                    [InlineKeyboardButton(text=("✨ Упростить" if user_lang_cb == "ru" else "✨ Simplify"), callback_data=f"edit_simplify_{full_key}"),
                     InlineKeyboardButton(text=("📌 Примеры" if user_lang_cb == "ru" else "📌 Examples"), callback_data=f"edit_examples_{full_key}")]
                ]
                kb = InlineKeyboardMarkup(inline_keyboard=buttons)
                await callback_query.message.answer(format_answer(user_lang_cb, response), reply_markup=kb, parse_mode="HTML")
        
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
    if any(word in text for word in IMAGE_KEYWORDS):
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
            system_prompt = DEFAULT_SYSTEM_PROMPT + get_mode_instruction(user_id)
            if pa_enabled:
                # Получаем персональный контекст для пользователя
                user_context = await personal_assistant.get_user_context(user_id, message.text)
                
                # Используем персональный контекст
                response = await openai_chat_with_personal_context(
                    system_prompt, 
                    dialog_history, 
                    user_context,
                    user_model
                )
                
                # Обучаем персонального ассистента на основе диалога
                await personal_assistant.learn_from_dialogue(user_id, message.text, response)
            else:
                # Обычный режим без персонального контекста
                response = await openai_chat_with_history(system_prompt, dialog_history, user_model)
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
                user_lang_msg = await get_user_language(message.from_user.id)
                await message.answer(format_answer(user_lang_msg, response), parse_mode="HTML")
        else:
            # Отправляем текстовый ответ + кнопки
            user_lang_msg = await get_user_language(message.from_user.id)
            full_key = f"{message.from_user.id}_{hash(response)%1000000}"
            full_response_cache[full_key] = response
            response_cache[full_key] = response
            if len(response) > 800:
                preview = response[:800] + "…"
                buttons = [
                    [InlineKeyboardButton(text=("🔎 Показать полностью" if user_lang_msg == "ru" else "🔎 Show full"), callback_data=f"show_full_{full_key}")],
                    [InlineKeyboardButton(text=("🔁 Переформулировать" if user_lang_msg == "ru" else "🔁 Rephrase"), callback_data=f"rephrase_{full_key}")],
                    [InlineKeyboardButton(text=("✨ Упростить" if user_lang_msg == "ru" else "✨ Simplify"), callback_data=f"edit_simplify_{full_key}"),
                     InlineKeyboardButton(text=("📌 Примеры" if user_lang_msg == "ru" else "📌 Examples"), callback_data=f"edit_examples_{full_key}")]
                ]
                kb = InlineKeyboardMarkup(inline_keyboard=buttons)
                await message.answer(format_answer(user_lang_msg, preview), reply_markup=kb, parse_mode="HTML")
            else:
                buttons = [
                    [InlineKeyboardButton(text=("🔁 Переформулировать" if user_lang_msg == "ru" else "🔁 Rephrase"), callback_data=f"rephrase_{full_key}")],
                    [InlineKeyboardButton(text=("✨ Упростить" if user_lang_msg == "ru" else "✨ Simplify"), callback_data=f"edit_simplify_{full_key}"),
                     InlineKeyboardButton(text=("📌 Примеры" if user_lang_msg == "ru" else "📌 Examples"), callback_data=f"edit_examples_{full_key}")]
                ]
                kb = InlineKeyboardMarkup(inline_keyboard=buttons)
                await message.answer(format_answer(user_lang_msg, response), reply_markup=kb, parse_mode="HTML")
        
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
    port = os.getenv("PORT")
    
    # Для Railway webhook нужны WEBHOOK_URL и PORT
    use_webhook = (
        webhook_url and 
        webhook_url.strip() and 
        "your-app" not in webhook_url.lower() and
        port  # Railway автоматически ставит PORT
    )
    
    logger.info(f"🔍 Проверка переменных:")
    logger.info(f"   WEBHOOK_URL: {webhook_url}")
    logger.info(f"   PORT: {port}")
    logger.info(f"   Используем webhook: {use_webhook}")
    
    if use_webhook:
        logger.info(f"🌐 Используется WEBHOOK режим (безопасно для Railway): {webhook_url}")
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
                else:
                    logger.info("✅ Webhook работает без ошибок")
            
            # Ожидаем завершения
            try:
                while True:
                    await asyncio.sleep(3600)  # Просыпаемся каждый час
            except KeyboardInterrupt:
                logger.info("👋 Бот остановлен пользователем")
            finally:
                # Останавливаем сервер
                await runner.cleanup()
                logger.info("📊 Webhook сервер остановлен")
                
        except Exception as e:
            logger.error(f"💥 Ошибка в webhook режиме: {e}")
            logger.info("🔄 Переходим на polling режим...")
            use_webhook = False
    
    if not use_webhook:
        logger.info("🔄 Используется POLLING режим (для локальной разработки)")
        try:
            # Удаляем webhook перед поллингом
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("🗑️ Webhook удален перед polling")
            
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
