"""Callback handler for inline keyboard interactions."""

import logging
from aiogram import Router, types
from aiogram.filters import Text

from app.db import db
from app.utils.keyboards import (
    get_main_menu_keyboard, get_persona_keyboard, get_language_keyboard,
    get_tools_keyboard, get_plan_keyboard
)
from app.utils.texts import (
    get_menu_help_text, get_plan_info_text, 
    PERSONA_DESCRIPTIONS, LANGUAGE_NAMES
)

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


@router.callback_query(Text(startswith="menu:"))
async def handle_menu_callbacks(callback_query: types.CallbackQuery):
    """Handle main menu callbacks."""
    try:
        action = callback_query.data.split(":", 1)[1]
        
        if action == "chat":
            text = get_menu_help_text('chat')
            await callback_query.message.edit_text(
                text, reply_markup=get_main_menu_keyboard()
            )
        
        elif action == "image":
            text = get_menu_help_text('image')
            await callback_query.message.edit_text(
                text, reply_markup=get_main_menu_keyboard()
            )
        
        elif action == "voice":
            text = get_menu_help_text('voice')
            await callback_query.message.edit_text(
                text, reply_markup=get_main_menu_keyboard()
            )
        
        elif action == "tools":
            text = get_menu_help_text('tools')
            await callback_query.message.edit_text(
                text, reply_markup=get_tools_keyboard()
            )
        
        elif action == "reminder":
            text = get_menu_help_text('reminder')
            await callback_query.message.edit_text(
                text, reply_markup=get_main_menu_keyboard()
            )
        
        elif action == "plan":
            user = await db.get_user(callback_query.from_user.id)
            plan = user['plan'] if user else 'FREE'
            text = get_plan_info_text(plan)
            
            await callback_query.message.edit_text(
                text, reply_markup=get_plan_keyboard(plan)
            )
        
        elif action == "persona":
            user_session = await db.get_user_session(callback_query.from_user.id)
            current_persona = user_session.get('persona', 'default')
            
            text = f"👤 <b>Выбор персоны ИИ</b>\n\n"
            text += f"Текущая: {PERSONA_DESCRIPTIONS[current_persona]}\n\n"
            text += "Выберите стиль общения:\n\n"
            
            for persona, desc in PERSONA_DESCRIPTIONS.items():
                marker = "✅ " if persona == current_persona else "• "
                text += f"{marker}{desc}\n"
            
            await callback_query.message.edit_text(
                text, reply_markup=get_persona_keyboard()
            )
        
        elif action == "language":
            user_session = await db.get_user_session(callback_query.from_user.id)
            current_lang = user_session.get('language', 'ru')
            
            text = f"🌐 <b>Выбор языка</b>\n\n"
            text += f"Текущий: {LANGUAGE_NAMES[current_lang]}\n\n"
            text += "Выберите язык интерфейса:"
            
            await callback_query.message.edit_text(
                text, reply_markup=get_language_keyboard()
            )
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Menu callback error: {e}")
        await callback_query.answer("Произошла ошибка", show_alert=True)


@router.callback_query(Text(startswith="persona:"))
async def handle_persona_callbacks(callback_query: types.CallbackQuery):
    """Handle persona selection callbacks."""
    try:
        persona = callback_query.data.split(":", 1)[1]
        user_id = callback_query.from_user.id
        
        # Update user session
        session = await db.get_user_session(user_id)
        session['persona'] = persona
        await db.update_user_session(user_id, session)
        
        text = f"✅ Персона изменена на: {PERSONA_DESCRIPTIONS[persona]}"
        
        await callback_query.message.edit_text(
            text, reply_markup=get_main_menu_keyboard()
        )
        await callback_query.answer("Персона обновлена!")
        
    except Exception as e:
        logger.error(f"Persona callback error: {e}")
        await callback_query.answer("Произошла ошибка", show_alert=True)


@router.callback_query(Text(startswith="lang:"))
async def handle_language_callbacks(callback_query: types.CallbackQuery):
    """Handle language selection callbacks."""
    try:
        language = callback_query.data.split(":", 1)[1]
        user_id = callback_query.from_user.id
        
        # Update user session
        session = await db.get_user_session(user_id)
        session['language'] = language
        await db.update_user_session(user_id, session)
        
        text = f"✅ Язык изменен на: {LANGUAGE_NAMES[language]}"
        
        await callback_query.message.edit_text(
            text, reply_markup=get_main_menu_keyboard()
        )
        await callback_query.answer("Язык обновлен!")
        
    except Exception as e:
        logger.error(f"Language callback error: {e}")
        await callback_query.answer("Произошла ошибка", show_alert=True)


@router.callback_query(Text(startswith="tool:"))
async def handle_tool_callbacks(callback_query: types.CallbackQuery):
    """Handle tool selection callbacks."""
    try:
        tool = callback_query.data.split(":", 1)[1]
        
        help_texts = {
            'wiki': "📖 Введите: <code>wiki [запрос]</code>\nПример: <code>wiki Эйнштейн</code>",
            'weather': "🌤 Введите: <code>погода [город]</code>\nПример: <code>погода Москва</code>",
            'calc': "🧮 Введите: <code>calc [выражение]</code>\nПример: <code>calc 2+2*3</code>",
            'translate': "🔄 Введите: <code>переведи [текст]</code>\nПример: <code>переведи hello world</code>"
        }
        
        text = help_texts.get(tool, "Инструмент недоступен")
        
        await callback_query.message.edit_text(
            text, reply_markup=get_tools_keyboard()
        )
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Tool callback error: {e}")
        await callback_query.answer("Произошла ошибка", show_alert=True)


@router.callback_query(Text(startswith="back:"))
async def handle_back_callbacks(callback_query: types.CallbackQuery):
    """Handle back button callbacks."""
    try:
        destination = callback_query.data.split(":", 1)[1]
        
        if destination == "main":
            # Get user stats for welcome message
            from app.utils.texts import WELCOME_TEXT, get_user_stats_text
            
            stats_text = await get_user_stats_text(callback_query.from_user.id)
            welcome_message = WELCOME_TEXT.format(
                name=callback_query.from_user.first_name or "пользователь",
                stats=stats_text
            )
            
            await callback_query.message.edit_text(
                welcome_message, reply_markup=get_main_menu_keyboard()
            )
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Back callback error: {e}")
        await callback_query.answer("Произошла ошибка", show_alert=True)


@router.callback_query()
async def handle_unknown_callbacks(callback_query: types.CallbackQuery):
    """Handle unknown callback queries."""
    logger.warning(f"Unknown callback: {callback_query.data}")
    await callback_query.answer("Неизвестная команда", show_alert=True)