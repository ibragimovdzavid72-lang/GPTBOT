"""
Основной модуль Telegram‑бота с поддержкой команды /suggest_prompt и логированием.

Этот модуль использует библиотеку aiogram v3 для асинхронной работы с
Telegram‑API, а также асинхронный драйвер asyncpg для записи логов в
PostgreSQL. Он подключается к OpenAI через модуль ai для генерации
ответов на сообщения пользователей.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
import asyncpg

from .config import settings
from .suggest import generate_prompt_from_logs
from .ai import openai_chat


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Пул подключений к базе данных (инициализируется при запуске)
pool: asyncpg.pool.Pool | None = None

# Системный промпт по умолчанию для диалогов
DEFAULT_SYSTEM_PROMPT = (
    "Вы helpful AI‑ассистент в Telegram. Давайте краткие, точные и полезные ответы."
)


async def on_startup() -> None:
    """Функция, вызываемая при запуске бота."""
    global pool
    try:
        pool = await asyncpg.create_pool(settings.DATABASE_URL)
        logger.info("Подключение к базе данных установлено")
    except Exception as e:
        pool = None
        logger.error(f"Не удалось подключиться к базе данных: {e}")


async def on_shutdown() -> None:
    """Функция, вызываемая при остановке бота."""
    global pool
    if pool:
        await pool.close()
        logger.info("Подключение к базе данных закрыто")


@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """Обработчик команды /start."""
    await message.answer(
        "Привет! Я Telegram‑бот с искусственным интеллектом. "
        "Отправьте мне любое сообщение, и я отвечу с помощью OpenAI."
    )


@dp.message(Command("suggest_prompt"))
async def cmd_suggest_prompt(message: types.Message) -> None:
    """Обработчик команды /suggest_prompt для генерации улучшенного промпта."""
    if not pool:
        await message.answer("Нет подключения к базе данных.")
        return
    try:
        suggestion = await generate_prompt_from_logs(pool)
        await message.answer(f"Предложенный промпт:\n\n{suggestion}")
    except Exception as e:
        logger.error(f"Ошибка в suggest_prompt: {e}")
        await message.answer("Извините, не удалось сгенерировать предложение сейчас.")


@dp.message()
async def handle_message(message: types.Message) -> None:
    """Обработчик всех текстовых сообщений."""
    # Игнорируем сообщения без текста
    if not message.text:
        return
    try:
        # Получаем ответ от OpenAI
        response = await openai_chat(DEFAULT_SYSTEM_PROMPT, message.text)
        # Усечение длинных ответов для Telegram
        if len(response) > settings.MAX_TG_REPLY:
            response = response[: settings.MAX_TG_REPLY] + "... (ответ усечён)"
        # Отправляем ответ пользователю
        await message.answer(response)
        # Записываем взаимодействие в базу
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO logs (username, command, args, answer) VALUES ($1, $2, $3, $4)",
                    message.from_user.username,
                    "message",
                    message.text,
                    response,
                )
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await message.answer("Извините, произошла ошибка при обработке вашего сообщения.")


async def main() -> None:
    """Основная функция запуска бота."""
    # Регистрируем обработчики запуска и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    # Запускаем polling (опрос)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
