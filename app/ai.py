"""
Модуль для взаимодействия с OpenAI. Содержит функции для отправки
запросов к чат‑модели и получения ответов. Использует асинхронный
клиент OpenAI для эффективной работы.
"""

import openai
from .config import settings

# Инициализация асинхронного клиента OpenAI. Требуется API‑ключ, который
# должен быть задан в переменной окружения OPENAI_API_KEY.
client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def openai_chat(system_prompt: str, user_message: str) -> str:
    """
    Отправляет запрос к модели OpenAI и возвращает ответ.

    :param system_prompt: Системный промпт, задающий контекст и стиль ответов.
    :param user_message: Сообщение пользователя, на которое нужно ответить.
    :return: Ответ модели в виде строки.
    :raises Exception: При ошибке взаимодействия с API.
    """
    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=settings.TEMPERATURE,
            timeout=settings.REQUEST_TIMEOUT,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise Exception(f"Ошибка при вызове OpenAI API: {str(e)}")


async def openai_chat_with_history(system_prompt: str, messages: list) -> str:
    """
    Отправляет запрос к модели OpenAI с историей сообщений.

    :param system_prompt: Системный промпт для управления поведением ИИ.
    :param messages: Список сообщений с полями 'role' и 'content'.
    :return: Ответ модели.
    :raises Exception: При ошибке взаимодействия с API.
    """
    try:
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=full_messages,
            temperature=settings.TEMPERATURE,
            timeout=settings.REQUEST_TIMEOUT,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise Exception(f"Ошибка при вызове OpenAI API: {str(e)}")
