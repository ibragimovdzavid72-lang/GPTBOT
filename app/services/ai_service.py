"""
AI service for OpenAI interactions.
Выделенный сервис для работы с OpenAI API.
"""

import asyncio
import logging
import tempfile
import os
from typing import Dict, List, Optional, Any

from ..ai import (
    openai_chat, openai_image, openai_vision, 
    openai_tts, openai_stt, openai_chat_with_history, 
    openai_chat_with_personal_context
)
from ..constants import DEFAULT_SYSTEM_PROMPT, MAX_TTS_LENGTH, TTS_VOICES
from .database_service import database_service
from .user_service import user_service
from ..config import settings

logger = logging.getLogger(__name__)


class AIService:
    """Сервис для работы с OpenAI API."""
    
    def __init__(self):
        """Инициализация AI сервиса."""
        self.default_system_prompt = DEFAULT_SYSTEM_PROMPT
    
    async def generate_text_response(
        self, 
        user_id: int, 
        user_message: str, 
        system_prompt: Optional[str] = None,
        use_history: bool = True
    ) -> str:
        """Генерирует текстовый ответ с учетом истории диалога."""
        try:
            # Получаем модель пользователя
            user_model = await user_service.get_user_model(user_id)
            
            # Используем системный промпт
            prompt = system_prompt or self.default_system_prompt
            
            if use_history:
                # Получаем историю диалога
                dialog_history = await database_service.get_dialog_history(user_id, limit=10)
                
                # Добавляем текущее сообщение
                dialog_history.append({"role": "user", "content": user_message})
                
                # Генерируем ответ с историей
                response = await openai_chat_with_history(prompt, dialog_history, user_model)
            else:
                # Генерируем простой ответ
                response = await openai_chat(user_message, user_model)
            
            # Ограничиваем длину ответа
            if len(response) > settings.MAX_TG_REPLY:
                response = response[:settings.MAX_TG_REPLY] + "... (ответ усечён)"
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating text response: {e}")
            return "❌ Извините, сейчас проблемы с AI сервисом. Попробуйте позже."
    
    async def generate_image(self, prompt: str, size: str = "1024x1024") -> Optional[str]:
        """Генерирует изображение по промпту."""
        try:
            return await openai_image(prompt, size)
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None
    
    async def analyze_image(self, image_data: bytes) -> Optional[str]:
        """Анализирует изображение через OpenAI Vision."""
        try:
            return await openai_vision(image_data)
        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            return None
    
    async def generate_voice_response(self, user_id: int, text: str) -> Optional[bytes]:
        """Генерирует голосовой ответ."""
        try:
            if len(text) > MAX_TTS_LENGTH:
                return None
            
            # Получаем голос пользователя
            tts_voice = await user_service.get_user_tts_voice(user_id)
            
            # Генерируем аудио
            return await openai_tts(text, tts_voice)
            
        except Exception as e:
            logger.error(f"Error generating voice response: {e}")
            return None
    
    async def transcribe_voice(self, audio_data: bytes) -> Optional[str]:
        """Распознает голосовое сообщение."""
        try:
            return await openai_stt(audio_data)
        except Exception as e:
            logger.error(f"Error transcribing voice: {e}")
            return None
    
    async def process_voice_message(
        self, 
        user_id: int, 
        audio_data: bytes, 
        voice_response: bool = False
    ) -> Dict[str, Any]:
        """Обрабатывает голосовое сообщение полностью."""
        try:
            # Распознаем голос
            transcribed_text = await self.transcribe_voice(audio_data)
            if not transcribed_text:
                return {
                    "success": False,
                    "error": "Не удалось распознать голосовое сообщение"
                }
            
            # Генерируем текстовый ответ
            text_response = await self.generate_text_response(user_id, transcribed_text)
            
            result = {
                "success": True,
                "transcribed_text": transcribed_text,
                "text_response": text_response,
                "voice_response": None
            }
            
            # Генерируем голосовой ответ если нужно
            if voice_response:
                voice_data = await self.generate_voice_response(user_id, text_response)
                if voice_data:
                    result["voice_response"] = voice_data
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            return {
                "success": False,
                "error": "Ошибка при обработке голосового сообщения"
            }
    
    async def save_dialog_interaction(
        self, 
        user_id: int, 
        user_message: str, 
        ai_response: str
    ) -> bool:
        """Сохраняет взаимодействие в историю диалога."""
        try:
            # Сохраняем сообщение пользователя
            await database_service.save_dialog_message(user_id, "user", user_message)
            
            # Сохраняем ответ ассистента
            await database_service.save_dialog_message(user_id, "assistant", ai_response)
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving dialog interaction: {e}")
            return False
    
    async def generate_personal_response(
        self, 
        user_id: int, 
        user_message: str
    ) -> str:
        """Генерирует персонализированный ответ с учетом контекста пользователя."""
        try:
            # Получаем модель пользователя
            user_model = await user_service.get_user_model(user_id)
            
            # Используем персональный контекст
            response = await openai_chat_with_personal_context(
                user_id, 
                user_message, 
                user_model
            )
            
            # Ограничиваем длину ответа
            if len(response) > settings.MAX_TG_REPLY:
                response = response[:settings.MAX_TG_REPLY] + "... (ответ усечён)"
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating personal response: {e}")
            return "❌ Извините, сейчас проблемы с персональным ассистентом. Попробуйте позже."
    
    def create_temp_audio_file(self, audio_data: bytes) -> str:
        """Создает временный аудио файл."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_file.write(audio_data)
            return temp_file.name
    
    def cleanup_temp_file(self, file_path: str) -> None:
        """Удаляет временный файл."""
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.error(f"Error cleaning up temp file: {e}")


# Глобальный экземпляр сервиса
ai_service = AIService()