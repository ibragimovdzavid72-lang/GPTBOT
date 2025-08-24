"""Reminders handler for scheduling notifications."""

import logging
import re
from datetime import datetime, timedelta
from aiogram import Router, types
from aiogram.filters import Text

from app.db import db
from app.utils.keyboards import get_main_menu_keyboard
from app.services.openai_service import rate_limiter

logger = logging.getLogger(__name__)
router = Router(name="reminders")


def parse_reminder_time(text: str) -> tuple[str, datetime]:
    """
    Parse reminder text and extract reminder time.
    Returns (reminder_text, reminder_datetime)
    """
    # Pattern for "напомни [text] в [DD.MM HH:MM]"
    pattern1 = r'напомни\s+(.+?)\s+в\s+(\d{1,2}\.\d{1,2})\s+(\d{1,2}:\d{2})'
    match1 = re.search(pattern1, text, re.IGNORECASE)
    
    if match1:
        reminder_text = match1.group(1).strip()
        date_str = match1.group(2)
        time_str = match1.group(3)
        
        # Parse date
        day, month = map(int, date_str.split('.'))
        hour, minute = map(int, time_str.split(':'))
        
        # Get current year
        current_year = datetime.now().year
        
        try:
            reminder_dt = datetime(current_year, month, day, hour, minute)
            
            # If the date is in the past, assume next year
            if reminder_dt < datetime.now():
                reminder_dt = reminder_dt.replace(year=current_year + 1)
            
            return reminder_text, reminder_dt
        except ValueError:
            raise ValueError("Неверная дата или время")
    
    # Pattern for "напомни [text] через [N] [unit]"
    pattern2 = r'напомни\s+(.+?)\s+через\s+(\d+)\s+(минут|час|часа|часов|день|дня|дней)'
    match2 = re.search(pattern2, text, re.IGNORECASE)
    
    if match2:
        reminder_text = match2.group(1).strip()
        amount = int(match2.group(2))
        unit = match2.group(3).lower()
        
        now = datetime.now()
        
        if unit in ['минут']:
            reminder_dt = now + timedelta(minutes=amount)
        elif unit in ['час', 'часа', 'часов']:
            reminder_dt = now + timedelta(hours=amount)
        elif unit in ['день', 'дня', 'дней']:
            reminder_dt = now + timedelta(days=amount)
        else:
            raise ValueError("Неподдерживаемая единица времени")
        
        return reminder_text, reminder_dt
    
    # Pattern for "напомни [text] завтра в [HH:MM]"
    pattern3 = r'напомни\s+(.+?)\s+завтра\s+в\s+(\d{1,2}:\d{2})'
    match3 = re.search(pattern3, text, re.IGNORECASE)
    
    if match3:
        reminder_text = match3.group(1).strip()
        time_str = match3.group(2)
        
        hour, minute = map(int, time_str.split(':'))
        
        tomorrow = datetime.now() + timedelta(days=1)
        reminder_dt = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        return reminder_text, reminder_dt
    
    raise ValueError("Не удалось распознать формат напоминания")


@router.message(Text(startswith="напомни "))
async def handle_reminder(message: types.Message):
    """Handle reminder creation."""
    try:
        user_id = message.from_user.id
        text = message.text.strip()
        
        # Check rate limiting
        if not await rate_limiter.is_allowed(user_id):
            await message.answer("⏱ Слишком много запросов. Попробуйте через минуту.")
            return
        
        try:
            # Parse reminder
            reminder_text, reminder_time = parse_reminder_time(text)
            
            if len(reminder_text) > 500:
                await message.answer(
                    "⏰ Текст напоминания слишком длинный (максимум 500 символов).",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Check if time is not too far in the future (1 year max)
            if reminder_time > datetime.now() + timedelta(days=365):
                await message.answer(
                    "⏰ Напоминание не может быть установлено более чем на год вперед.",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Check if time is not in the past (with 1 minute tolerance)
            if reminder_time < datetime.now() - timedelta(minutes=1):
                await message.answer(
                    "⏰ Нельзя установить напоминание на прошедшее время.",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Create reminder in database
            reminder_id = await db.add_reminder(user_id, reminder_text, reminder_time)
            
            # Format response
            time_str = reminder_time.strftime("%d.%m.%Y в %H:%M")
            response = f"✅ <b>Напоминание установлено!</b>\n\n"
            response += f"📝 <b>Текст:</b> {reminder_text}\n"
            response += f"⏰ <b>Время:</b> {time_str}\n\n"
            response += f"ID напоминания: #{reminder_id}"
            
            await message.answer(response, reply_markup=get_main_menu_keyboard())
            
            # Log successful usage
            await db.log_usage(
                user_id, 'reminder_created', None, 'success',
                {
                    'reminder_id': reminder_id,
                    'reminder_text': reminder_text,
                    'reminder_time': reminder_time.isoformat()
                }
            )
            
        except ValueError as e:
            # Invalid format
            help_text = """
⏰ <b>Неверный формат напоминания</b>

<b>Поддерживаемые форматы:</b>

1️⃣ <code>напомни [текст] в [ДД.ММ ЧЧ:ММ]</code>
   Пример: <code>напомни купить молоко в 25.12 18:00</code>

2️⃣ <code>напомни [текст] через [N] [единица]</code>
   Пример: <code>напомни позвонить маме через 2 часа</code>
   Единицы: минут, час/часа/часов, день/дня/дней

3️⃣ <code>напомни [текст] завтра в [ЧЧ:ММ]</code>
   Пример: <code>напомни встреча завтра в 10:30</code>

Попробуйте еще раз с правильным форматом.
"""
            await message.answer(help_text, reply_markup=get_main_menu_keyboard())
        
    except Exception as e:
        logger.error(f"Reminder handler error: {e}")
        await message.answer(
            "😔 Произошла ошибка при создании напоминания. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )