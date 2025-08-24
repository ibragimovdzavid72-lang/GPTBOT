"""Background service for sending reminders."""

import asyncio
import logging
from datetime import datetime

from app.db import db
from app.bot import get_bot
from app.utils.keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)


async def start_reminder_service():
    """Start the background reminder service."""
    logger.info("Starting reminder service...")
    
    while True:
        try:
            await check_and_send_reminders()
            await asyncio.sleep(30)  # Check every 30 seconds
        except asyncio.CancelledError:
            logger.info("Reminder service cancelled")
            break
        except Exception as e:
            logger.error(f"Reminder service error: {e}")
            await asyncio.sleep(60)  # Wait longer on error


async def check_and_send_reminders():
    """Check for pending reminders and send them."""
    try:
        bot = get_bot()
        pending_reminders = await db.get_pending_reminders()
        
        for reminder in pending_reminders:
            try:
                user_id = reminder['user_id']
                text = reminder['text']
                reminder_id = reminder['id']
                remind_at = reminder['remind_at']
                
                # Format reminder message
                time_str = remind_at.strftime("%d.%m.%Y в %H:%M")
                message = f"⏰ <b>Напоминание!</b>\n\n"
                message += f"📝 {text}\n\n"
                message += f"🕐 Время: {time_str}\n"
                message += f"ID: #{reminder_id}"
                
                # Send reminder
                await bot.send_message(
                    chat_id=user_id,
                    text=message,
                    reply_markup=get_main_menu_keyboard()
                )
                
                # Mark as sent
                await db.mark_reminder_sent(reminder_id)
                
                # Log successful delivery
                await db.log_usage(
                    user_id, 'reminder_sent', None, 'success',
                    {
                        'reminder_id': reminder_id,
                        'reminder_text': text,
                        'scheduled_time': remind_at.isoformat()
                    }
                )
                
                logger.info(f"Reminder {reminder_id} sent to user {user_id}")
                
            except Exception as e:
                logger.error(f"Failed to send reminder {reminder['id']}: {e}")
                
                # Log failed delivery
                await db.log_usage(
                    reminder['user_id'], 'reminder_sent', None, 'error',
                    {
                        'reminder_id': reminder['id'],
                        'error': str(e)
                    }
                )
        
        if pending_reminders:
            logger.info(f"Processed {len(pending_reminders)} pending reminders")
            
    except Exception as e:
        logger.error(f"Error checking reminders: {e}")