import asyncio, logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from settings import BOT_TOKEN
from db import init_db, SessionLocal, due_reminders, mark_reminder_done
from handlers import router

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(); dp.include_router(router)

async def reminder_worker():
    await asyncio.sleep(5)
    while True:
        try:
            async with SessionLocal() as s:
                items = await due_reminders(s)
                for r in items:
                    try:
                        await bot.send_message(r.chat_id, f"⏰ Напоминание: {r.task}")
                        await mark_reminder_done(s, r.id)
                    except Exception as e:
                        logging.error("reminder send error: %s", e)
                await s.commit()
        except Exception as e:
            logging.error("reminder loop: %s", e)
        await asyncio.sleep(60)

async def set_commands():
    await bot.set_my_commands([BotCommand(command="start", description="Запуск бота")])

async def main():
    await init_db()
    await set_commands()
    asyncio.create_task(reminder_worker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
