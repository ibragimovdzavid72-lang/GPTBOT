"""Start command handler with main menu."""

import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.db import db
from app.utils.keyboards import get_main_menu_keyboard
from app.utils.texts import WELCOME_TEXT, get_user_stats_text

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command."""
    try:
        user = message.from_user
        
        # Create or update user in database
        user_data = {
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'language_code': user.language_code or 'ru'
        }
        
        db_user = await db.create_or_update_user(user_data)
        logger.info(f"User {user.id} started bot (plan: {db_user['plan']})")
        
        # Get user's daily statistics
        stats_text = await get_user_stats_text(user.id)
        
        # Send welcome message with main menu
        welcome_message = WELCOME_TEXT.format(
            name=user.first_name or user.username or "пользователь",
            stats=stats_text
        )
        
        await message.answer(
            welcome_message,
            reply_markup=get_main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error in start handler: {e}")
        await message.answer("Произошла ошибка при запуске бота. Попробуйте позже.")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Handle /help command."""
    help_text = """
🤖 <b>Помощь по боту</b>

<b>Основные функции:</b>
💬 <b>Чат</b> - Общение с ИИ с памятью разговора
🎨 <b>Изображения</b> - Генерация, анализ и редактирование
🔊 <b>Голос</b> - Распознавание речи и синтез голоса
🛠 <b>Инструменты</b> - Википедия, погода, калькулятор
⏰ <b>Напоминания</b> - Установка напоминаний на время
💳 <b>Тарифы</b> - Управление подпиской

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
/buy - Тарифы и оплата
/stats - Статистика (для админов)
/mode - Смена персоны ИИ
/lang - Смена языка

<b>Примеры использования:</b>
• Просто напишите сообщение для чата с ИИ
• Отправьте фото для анализа
• Напишите "сгенерируй котенка" для создания изображения
• Отправьте голосовое сообщение
• "wiki Москва" - поиск в Википедии
• "погода Москва" - прогноз погоды
• "calc 2+2*3" - калькулятор
• "напомни купить молоко в 18:00" - напоминание

Используйте кнопки меню для быстрого доступа к функциям!
    """
    
    await message.answer(help_text, reply_markup=get_main_menu_keyboard())