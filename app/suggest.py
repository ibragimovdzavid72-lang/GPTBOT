"""
Модуль генерации предложений для улучшения промптов. Использует логи
диалогов из базы данных для анализа последних взаимодействий и
формирует рекомендации, обращаясь к OpenAI.
"""

from typing import List

import asyncpg

from .ai import openai_chat


async def generate_prompt_from_logs(pool: asyncpg.pool.Pool) -> str:
    """
    Анализирует последние записи логов и предлагает улучшенный промпт.

    :param pool: Пул подключений к базе данных PostgreSQL.
    :return: Сгенерированный текст предложения.
    """
    try:
        # Извлекаем последние 10 сообщений из логов
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT args FROM logs ORDER BY created_at DESC LIMIT 10"
            )

        # Собираем текст последних сообщений пользователя
        messages: List[str] = [row["args"] for row in rows if row["args"]]

        # Формируем запрос к OpenAI: попросим модель улучшить будущий промпт
        system_prompt = (
            "Ты — ассистент, который помогает формулировать более чёткие и "
            "эффективные запросы к ИИ. На основе последних обращений пользователей "
            "предложи новый, улучшенный промпт."
        )
        user_message = "\n".join(messages) or "Нет данных для анализа, предложи общий полезный промпт."

        # Отправляем запрос к модели
        suggestion = await openai_chat(system_prompt, user_message)
        return suggestion
    except Exception as e:
        # В случае ошибки возвращаем стандартное сообщение
        return "Извините, не удалось сгенерировать предложение. Попробуйте позже."