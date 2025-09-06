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
        """Показать страницу версий AI Agent-PRO."""
        from ..main import get_text
        
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
        
        return await safe_edit_with_navigation(
            callback_query=callback_query,
            content_text=versions_text,
            back_callback="back_to_main",
            back_text=get_text("back", user_lang)
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


# Глобальный экземпляр для использования в handlers
message_flow = MessageFlow()