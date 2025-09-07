"""
Утилиты для редактирования сообщений в Telegram боте.
Паттерн Anti-clutter Message Editing для чистого интерфейса.
"""

import logging
from typing import Optional, List
# Note: These imports may show errors in IDE but work at runtime
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)


async def safe_edit_message(
    callback_query: types.CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML"
) -> bool:
    """
    Безопасное редактирование сообщения с fallback.
    
    Args:
        callback_query: Callback запрос от кнопки
        text: Новый текст сообщения  
        reply_markup: Клавиатура (опционально)
        parse_mode: Режим парсинга (HTML/Markdown)
    
    Returns:
        bool: True если edit удался, False если использовался fallback
    """
    try:
        await callback_query.message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        logger.debug(f"✅ Message edited successfully for user {callback_query.from_user.id}")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ Edit failed, using fallback: {e}")
        
        # Fallback к новому сообщению
        try:
            await callback_query.message.answer(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            logger.debug(f"✅ Fallback message sent for user {callback_query.from_user.id}")
            # Пытаемся удалить предыдущее сообщение, чтобы меню было "исчезающим"
            try:
                await callback_query.message.delete()
            except Exception as del_err:
                logger.debug(f"(ignore) failed to delete previous message: {del_err}")
            return False
            
        except Exception as fallback_error:
            logger.error(f"❌ Both edit and fallback failed: {fallback_error}")
            await callback_query.answer("❌ Произошла ошибка. Попробуйте /start", show_alert=True)
            return False


async def safe_edit_with_navigation(
    callback_query: types.CallbackQuery,
    content_text: str,
    back_callback: str = "back_to_main",
    back_text: str = "⬅️ Назад",
    additional_buttons: Optional[List[List[InlineKeyboardButton]]] = None,
    parse_mode: str = "HTML"
) -> bool:
    """
    Редактирование сообщения с автоматической навигацией "Назад".
    
    Args:
        callback_query: Callback запрос
        content_text: Основной контент сообщения
        back_callback: Callback data для кнопки "Назад" 
        back_text: Текст кнопки "Назад"
        additional_buttons: Дополнительные кнопки [[button1, button2], [button3]]
        parse_mode: Режим парсинга
    
    Returns:
        bool: True если edit удался
    """
    
    # Строим клавиатуру
    keyboard = []
    
    # Добавляем дополнительные кнопки если есть
    if additional_buttons:
        keyboard.extend(additional_buttons)
    
    # Добавляем кнопку "Назад"
    keyboard.append([InlineKeyboardButton(text=back_text, callback_data=back_callback)])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    return await safe_edit_message(
        callback_query=callback_query,
        text=content_text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )


class MessageFlow:
    """Класс для управления потоком сообщений в боте."""
    
    def __init__(self):
        self.user_states = {}
    
    async def show_main_menu(self, callback_query: types.CallbackQuery, user_lang: str = "ru"):
        """Показать главное меню с правильной клавиатурой для пользователя."""
        from ..main import get_text, get_main_menu, get_admin_menu, is_super_admin
        
        welcome_text = get_text("welcome", user_lang)
        
        if is_super_admin(callback_query.from_user.id):
            menu = get_admin_menu(user_lang)
        else:
            menu = get_main_menu(user_lang)
        
        return await safe_edit_message(
            callback_query=callback_query,
            text=welcome_text,
            reply_markup=menu
        )
    
    async def show_pro_versions(self, callback_query: types.CallbackQuery, user_lang: str = "ru"):
        """Показать страницу версий AI Agent-PRO с RU/EN и кнопкой 🌐."""
        from ..main import get_text

        if user_lang == "en":
            versions_text = (
                "<b>⚡ AI Agent – Versions</b>\n\n"
                "🔹 FREE\n"
                "– Basic functions (chat, translations, simple texts)\n"
                "– Limited number of messages\n"
                "– No visual content\n\n"
                "🔹 PRO\n"
                "– Everything from FREE +\n"
                "– Work with files and documents\n"
                "– Image generation\n"
                "– Copywriting, rewriting, SEO\n"
                "– OCR (text recognition from images)\n\n"
                "🔹 ULTRA\n"
                "– Everything from PRO +\n"
                "– API integration (ChatGPT, MidJourney)\n"
                "– Unlimited visual content\n"
                "– Team collaboration\n"
                "– Priority processing speed\n\n"
                "⸻\n\n"
                "📌 <b>AI Agent Features</b>\n"
                "• 👩‍🎓 Students (essays, theses, coursework, reports)\n"
                "• ✍️ Copywriters (100% unique texts, rewriting, bypass AI detectors, plagiarism check bypass)\n"
                "• 📱 Bloggers (content plans, headlines, storytelling, scripts for blogs & Reels)\n"
                "• 🔎 SEO specialists (articles, search engine parsing, keyword analysis)\n"
                "• 🖼️ OCR — text recognition from images (photos)\n"
                "• 🚀 And much more!"
            )
            toggle_text = "🌐 Русский"
            back_text = get_text("back", "en")
        else:
            versions_text = (
                "<b>⚡ AI Agent – версии</b>\n\n"
                "🔹 FREE\n"
                "– Базовый функционал (чат, переводы, простые тексты)\n"
                "– Ограниченный лимит сообщений\n"
                "– Без визуального контента\n\n"
                "🔹 PRO\n"
                "– Всё из FREE +\n"
                "– Работа с файлами и документами\n"
                "– Генерация изображений\n"
                "– Копирайтинг, рерайтинг, SEO\n"
                "– OCR (распознавание текста с картинок)\n\n"
                "🔹 ULTRA\n"
                "– Всё из PRO +\n"
                "– Подключение к API (ChatGPT, MidJourney)\n"
                "– Визуальный контент без ограничений\n"
                "– Командная работа\n"
                "– Приоритетная скорость\n\n"
                "⸻\n\n"
                "📌 <b>Функционал AI Agent</b>\n"
                "• 👩‍🎓 Студенты (дипломы, эссе, курсовые, рефераты)\n"
                "• ✍️ Копирайтеры (100% уникальные тексты, рерайт, обход ИИ-детектора, обход «Антиплагиат»)\n"
                "• 📱 Блогеры (контент-планы, заголовки, сторителлинг, сценарии для блога и Reels)\n"
                "• 🔎 SEO-специалисты (статьи, парсинг поисковых систем, анализ ключевых слов)\n"
                "• 🖼️ OCR — распознавание текста с картинок (фотографии)\n"
                "• 🚀 И многое другое!"
            )
            toggle_text = "🌐 English"
            back_text = get_text("back", "ru")

        toggle_button = [[InlineKeyboardButton(text=toggle_text, callback_data="toggle_versions_lang")]]

        return await safe_edit_with_navigation(
            callback_query=callback_query,
            content_text=versions_text,
            additional_buttons=toggle_button,
            back_callback="back_to_main",
            back_text=back_text
        )
    
    async def show_language_menu(self, callback_query: types.CallbackQuery, user_lang: str = "ru"):
        """Показать меню выбора языка."""
        from ..main import get_text
        
        menu_text = f"<b>{get_text('language_interface', user_lang)}</b>\n\n{get_text('select_language', user_lang)}"
        
        language_buttons = [
            [
                InlineKeyboardButton(text=get_text("russian", user_lang), callback_data="set_lang_ru"),
                InlineKeyboardButton(text=get_text("english", user_lang), callback_data="set_lang_en")
            ]
        ]
        
        return await safe_edit_with_navigation(
            callback_query=callback_query,
            content_text=menu_text,
            additional_buttons=language_buttons,
            back_callback="back_to_main",
            back_text=get_text("back", user_lang)
        )

    async def show_welcome_screen(self, callback_query: types.CallbackQuery, user_lang: str = "ru"):
        """Показать современный экран приветствия с кнопкой Старт / Start."""
        if user_lang == "en":
            title = "<b>⚡ AI Agent ⚡</b>\n"
            features = (
                "\n"  # пустая строка после заголовка
                "📂 Documents & files\n"
                "🧠 Problem solving\n"
                "😉 Content creation\n"
                "💻 Code assistance\n"
                "✍️ Copywriting & rewriting\n"
                "🎨 Visual content\n"
                "🖼️ Image generation\n"
                "🌍 Translation & summarization"
            )
            start_text = "🚀 Start / Start"
            lang_toggle = "🌐 Русский"
            lang_callback = "set_lang_ru"
        else:
            title = "<b>⚡ AI Agent ⚡</b>\n"
            features = (
                "\n"
                "📂 Работа с документами и файлами\n"
                "🧠 Решение задач разного уровня\n"
                "😉 Создание контента\n"
                "💻 Работа с кодом\n"
                "✍️ Копирайтинг и рерайтинг\n"
                "🎨 Визуальный контент\n"
                "🖼️ Генерация изображений\n"
                "🌍 Перевод и краткий пересказ"
            )
            start_text = "🚀 Старт / Start"
            lang_toggle = "🌐 English"
            lang_callback = "set_lang_en"

        content_text = f"{title}{features}"

        buttons = [
            [InlineKeyboardButton(text=start_text, callback_data="back_to_main")],
            [InlineKeyboardButton(text=lang_toggle, callback_data=lang_callback)],
        ]

        return await safe_edit_with_navigation(
            callback_query=callback_query,
            content_text=content_text,
            additional_buttons=buttons,
            back_callback="back_to_main",
            back_text="⬅️ Назад"
        )


# Глобальный экземпляр для использования в handlers
message_flow = MessageFlow()