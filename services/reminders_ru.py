"""Фоновая служба для отправки напоминаний."""

import asyncio
import logging
from datetime import datetime

from database_ru import база_данных
from telegram_ru import получить_бота
from utils.keyboards_ru import получить_главное_меню_клавиатуру

logger = logging.getLogger(__name__)


async def запустить_службу_напоминаний():
    """Запустить фоновую службу напоминаний."""
    logger.info("Запуск службы напоминаний...")
    
    while True:
        try:
            await проверить_и_отправить_напоминания()
            await asyncio.sleep(30)  # Проверка каждые 30 секунд
        except asyncio.CancelledError:
            logger.info("Служба напоминаний отменена")
            break
        except Exception as e:
            logger.error(f"Ошибка службы напоминаний: {e}")
            await asyncio.sleep(60)  # Ждать дольше при ошибке


async def проверить_и_отправить_напоминания():
    """Проверить ожидающие напоминания и отправить их."""
    try:
        бот = получить_бота()
        ожидающие_напоминания = await база_данных.получить_ожидающие_напоминания()
        
        for напоминание in ожидающие_напоминания:
            try:
                user_id = напоминание['user_id']
                текст = напоминание['text']
                reminder_id = напоминание['id']
                remind_at = напоминание['remind_at']
                
                # Форматирование сообщения напоминания
                время_строка = remind_at.strftime("%d.%m.%Y в %H:%M")
                сообщение = f"⏰ <b>Напоминание!</b>\n\n"
                сообщение += f"📝 {текст}\n\n"
                сообщение += f"🕐 Время: {время_строка}\n"
                сообщение += f"ID: #{reminder_id}"
                
                # Отправка напоминания
                await бот.send_message(
                    chat_id=user_id,
                    text=сообщение,
                    reply_markup=получить_главное_меню_клавиатуру()
                )
                
                # Отметить как отправленное
                await база_данных.отметить_напоминание_отправленным(reminder_id)
                
                # Записать успешную доставку
                await база_данных.записать_статистику(
                    user_id, 'reminder_sent', None, 'success',
                    {
                        'reminder_id': reminder_id,
                        'reminder_text': текст,
                        'scheduled_time': remind_at.isoformat()
                    }
                )
                
                logger.info(f"Напоминание {reminder_id} отправлено пользователю {user_id}")
                
            except Exception as e:
                logger.error(f"Не удалось отправить напоминание {напоминание['id']}: {e}")
                
                # Записать неудачную доставку
                await база_данных.записать_статистику(
                    напоминание['user_id'], 'reminder_sent', None, 'error',
                    {
                        'reminder_id': напоминание['id'],
                        'error': str(e)
                    }
                )
        
        if ожидающие_напоминания:
            logger.info(f"Обработано {len(ожидающие_напоминания)} ожидающих напоминаний")
            
    except Exception as e:
        logger.error(f"Ошибка при проверке напоминаний: {e}")