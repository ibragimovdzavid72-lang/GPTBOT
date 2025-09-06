"""
Модуль для взаимодействия с OpenAI. Содержит функции для отправки
запросов к чат‑модели и получения ответов. Использует асинхронный
клиент OpenAI для эффективной работы.
"""

import base64
import openai
from .config import settings

# Инициализация асинхронного клиента OpenAI. Требуется API‑ключ, который
# должен быть задан в переменной окружения OPENAI_API_KEY.
client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def openai_chat(system_prompt: str, user_message: str, model: str = None) -> str:
    """
    Отправляет запрос к модели OpenAI и возвращает ответ.

    :param system_prompt: Системный промпт, задающий контекст и стиль ответов.
    :param user_message: Сообщение пользователя, на которое нужно ответить.
    :param model: Модель OpenAI для использования (по умолчанию из настроек).
    :return: Ответ модели в виде строки.
    :raises Exception: При ошибке взаимодействия с API.
    """
    try:
        response = await client.chat.completions.create(
            model=model or settings.OPENAI_MODEL,
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


async def openai_chat_with_history(system_prompt: str, messages: list, model: str = None) -> str:
    """
    Отправляет запрос к модели OpenAI с историей сообщений.

    :param system_prompt: Системный промпт для управления поведением ИИ.
    :param messages: Список сообщений с полями 'role' и 'content'.
    :param model: Модель OpenAI для использования (по умолчанию из настроек).
    :return: Ответ модели.
    :raises Exception: При ошибке взаимодействия с API.
    """
    try:
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)
        response = await client.chat.completions.create(
            model=model or settings.OPENAI_MODEL,
            messages=full_messages,
            temperature=settings.TEMPERATURE,
            timeout=settings.REQUEST_TIMEOUT,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise Exception(f"Ошибка при вызове OpenAI API: {str(e)}")


async def openai_image(prompt: str, size: str = "1024x1024") -> str:
    """
    Генерирует изображение с помощью модели DALL-E от OpenAI.

    :param prompt: Описание изображения для генерации.
    :param size: Размер изображения ("512x512", "1024x1024", "1024x1792", "1792x1024").
    :return: URL сгенерированного изображения.
    :raises Exception: При ошибке взаимодействия с API.
    """
    try:
        # Выбираем модель в зависимости от размера
        model = "dall-e-3" if size in ["1024x1024", "1024x1792", "1792x1024"] else "dall-e-2"
        
        response = await client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
        )
        return response.data[0].url
    except Exception as e:
        raise Exception(f"Ошибка при генерации изображения: {str(e)}")


async def openai_vision(image_data: bytes, prompt: str = "Что изображено на картинке?") -> str:
    """
    Анализирует изображение с помощью модели Vision от OpenAI.

    :param image_data: Данные изображения в формате bytes.
    :param prompt: Вопрос о изображении (по умолчанию общий вопрос).
    :return: Ответ модели о содержимом изображения.
    :raises Exception: При ошибке взаимодействия с API.
    """
    try:
        # Кодируем изображение в base64
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise Exception(f"Ошибка при анализе изображения: {str(e)}")


async def openai_tts(text: str, voice: str = "alloy") -> bytes:
    """
    Преобразует текст в речь с помощью OpenAI TTS.

    :param text: Текст для преобразования в речь.
    :param voice: Голос для синтеза речи (alloy, echo, fable, onyx, nova, shimmer).
    :return: Аудиоданные в формате bytes.
    :raises Exception: При ошибке взаимодействия с API.
    """
    try:
        response = await client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        return response.content
    except Exception as e:
        raise Exception(f"Ошибка при синтезе речи: {str(e)}")


async def openai_stt(audio_path: str) -> str:
    """
    Преобразует аудио в текст с помощью OpenAI Whisper.

    :param audio_path: Путь к аудиофайлу для распознавания.
    :return: Распознанный текст.
    :raises Exception: При ошибке взаимодействия с API.
    """
    import tempfile
    import os
    
    converted_path = None
    try:
        # Проверяем формат файла и конвертируем при необходимости
        if audio_path.endswith('.ogg'):
            try:
                from pydub import AudioSegment
                # Конвертируем OGG в WAV для лучшей совместимости
                audio = AudioSegment.from_ogg(audio_path)
                
                # Создаем временный WAV файл
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                    converted_path = temp_file.name
                    
                audio.export(converted_path, format="wav")
                file_to_use = converted_path
            except ImportError:
                # Если pydub не установлен, используем оригинальный файл
                file_to_use = audio_path
        else:
            file_to_use = audio_path
            
        # Отправляем на распознавание в OpenAI Whisper
        with open(file_to_use, "rb") as audio_file:
            response = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        return response.strip() if hasattr(response, 'strip') else str(response).strip()
        
    except Exception as e:
        raise Exception(f"Ошибка при распознавании речи: {str(e)}")
    finally:
        # Удаляем временный файл если он был создан
        if converted_path and os.path.exists(converted_path):
            try:
                os.unlink(converted_path)
            except Exception:
                pass  # Игнорируем ошибки удаления
