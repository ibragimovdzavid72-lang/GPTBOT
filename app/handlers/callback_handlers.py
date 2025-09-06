"""
Обработчики callback-запросов для Telegram бота.
Разделение логики обработки кнопок от основного файла.
"""

import logging
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ..utils.message_editor import message_flow
from ..main import (
    get_text, is_super_admin, 
    get_main_menu, get_admin_menu
)
from ..services.user_service import user_service

logger = logging.getLogger(__name__)


async def handle_ai_agent_pro(callback_query: types.CallbackQuery) -> None:
    """Обработчик кнопки ⚡ AI Agent-PRO ⚡."""
    try:
        user_lang = await user_service.get_user_language(callback_query.from_user.id)
        await message_flow.show_pro_versions(callback_query, user_lang)
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in handle_ai_agent_pro: {e}")
        await callback_query.answer("❌ Произошла ошибка", show_alert=True)


async def handle_back_to_main(callback_query: types.CallbackQuery) -> None:
    """Обработчик кнопки ⬅️ Назад (возврат в главное меню)."""
    try:
        user_lang = await user_service.get_user_language(callback_query.from_user.id)
        await message_flow.show_main_menu(callback_query, user_lang)
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in handle_back_to_main: {e}")
        await callback_query.answer("❌ Произошла ошибка", show_alert=True)


async def handle_change_language(callback_query: types.CallbackQuery) -> None:
    """Обработчик кнопки смены языка."""
    try:
        user_lang = await user_service.get_user_language(callback_query.from_user.id)
        await message_flow.show_language_menu(callback_query, user_lang)
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in handle_change_language: {e}")
        await callback_query.answer("❌ Произошла ошибка", show_alert=True)


async def handle_set_language(callback_query: types.CallbackQuery, lang_code: str) -> None:
    """Обработчик установки языка (set_lang_ru, set_lang_en)."""
    try:
        # Устанавливаем язык пользователя
        success = await user_service.set_user_language(callback_query.from_user.id, lang_code)
        
        if success:
            # Показываем подтверждение и возвращаем в главное меню
            confirmation_text = get_text("language_set", lang_code, lang=lang_code)
            await callback_query.answer(confirmation_text, show_alert=True)
            
            # Обновляем главное меню на новом языке
            await message_flow.show_main_menu(callback_query, lang_code)
        else:
            await callback_query.answer("❌ Ошибка установки языка", show_alert=True)
            
    except Exception as e:
        logger.error(f"❌ Error in handle_set_language: {e}")
        await callback_query.answer("❌ Произошла ошибка", show_alert=True)


async def handle_web_search_menu(callback_query: types.CallbackQuery) -> None:
    """Обработчик меню поиска в интернете."""
    try:
        user_lang = await user_service.get_user_language(callback_query.from_user.id)
        
        search_text = (
            f"🔍 <b>{get_text('web_search', user_lang)}</b>\n\n"
            f"{get_text('search_help', user_lang)}\n\n"
            f"📝 <b>{get_text('search_placeholder', user_lang)}</b>\n"
            f"/search погода в Москве\n"
            f"/search курс доллара сегодня\n"
            f"/search новые технологии 2024"
        )
        
        back_button = [[InlineKeyboardButton(
            text=get_text("back", user_lang), 
            callback_data="ai_chat_menu"
        )]]
        
        menu = InlineKeyboardMarkup(inline_keyboard=back_button)
        
        await message_flow.safe_edit_message(
            callback_query=callback_query,
            text=search_text,
            reply_markup=menu
        )
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in handle_web_search_menu: {e}")
        await callback_query.answer("❌ Произошла ошибка", show_alert=True)


async def handle_news_search_menu(callback_query: types.CallbackQuery) -> None:
    """Обработчик меню поиска новостей."""
    try:
        user_lang = await user_service.get_user_language(callback_query.from_user.id)
        
        news_text = (
            f"📰 <b>{get_text('search_news', user_lang)}</b>\n\n"
            f"Используйте /news [запрос] для поиска последних новостей.\n\n"
            f"📝 <b>Примеры:</b>\n"
            f"/news технологии\n"
            f"/news экономика России\n"
            f"/news (без параметров) - общие новости"
        )
        
        back_button = [[InlineKeyboardButton(
            text=get_text("back", user_lang), 
            callback_data="ai_chat_menu"
        )]]
        
        menu = InlineKeyboardMarkup(inline_keyboard=back_button)
        
        await message_flow.safe_edit_message(
            callback_query=callback_query,
            text=news_text,
            reply_markup=menu
        )
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in handle_news_search_menu: {e}")
        await callback_query.answer("❌ Произошла ошибка", show_alert=True)


# Словарь маршрутизации callback-ов
CALLBACK_HANDLERS = {
    "ai_agent_pro": handle_ai_agent_pro,
    "back_to_main": handle_back_to_main,
    "change_language": handle_change_language,
    "web_search_menu": handle_web_search_menu,
    "news_search_menu": handle_news_search_menu,
    "set_lang_ru": lambda cb: handle_set_language(cb, "ru"),
    "set_lang_en": lambda cb: handle_set_language(cb, "en"),
}


async def route_callback(callback_query: types.CallbackQuery) -> None:
    """
    Маршрутизатор callback-запросов.
    Централизованная точка входа для всех callback-обработчиков.
    """
    handler_name = callback_query.data
    
    if handler_name in CALLBACK_HANDLERS:
        handler = CALLBACK_HANDLERS[handler_name]
        try:
            await handler(callback_query)
        except Exception as e:
            logger.error(f"❌ Error in callback handler {handler_name}: {e}")
            await callback_query.answer("❌ Произошла ошибка", show_alert=True)
    else:
        logger.warning(f"⚠️ Unhandled callback: {handler_name}")
        await callback_query.answer("⚠️ Неизвестная команда", show_alert=True)
