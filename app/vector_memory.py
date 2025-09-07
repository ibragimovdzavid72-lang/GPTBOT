"""
Модуль для работы с векторной памятью персонального ассистента.

Использует ChromaDB для хранения эмбеддингов пользовательских данных и
обеспечивает персонализированные ответы на основе истории взаимодействий.
"""

import logging
import os
import hashlib
from typing import List, Dict, Optional, Tuple
import asyncio
from concurrent.futures import ThreadPoolExecutor

import chromadb
from chromadb.config import Settings
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .config import settings
from .ai import client as openai_client

logger = logging.getLogger(__name__)


class PersonalAssistant:
    """Класс для управления персональным ассистентом с векторной памятью."""
    
    def __init__(self):
        """Инициализация векторной базы данных."""
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Настройка ChromaDB
        self.chroma_client = None
        self.collection = None
        self._initialize_db()
    
    def _initialize_db(self):
        """Инициализация ChromaDB."""
        try:
            # Создаем директорию для данных если её нет
            data_dir = os.path.join(os.getcwd(), "vector_data")
            os.makedirs(data_dir, exist_ok=True)
            
            # Инициализируем ChromaDB с персистентным хранилищем
            self.chroma_client = chromadb.PersistentClient(
                path=data_dir,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Создаем или получаем коллекцию для пользовательских данных
            self.collection = self.chroma_client.get_or_create_collection(
                name="user_memory",
                metadata={"description": "Персональная память пользователей"}
            )
            
            logger.info("✅ Векторная база данных инициализирована")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации векторной БД: {e}")
            self.chroma_client = None
            self.collection = None
    
    async def create_embedding(self, text: str) -> Optional[List[float]]:
        """
        Создает эмбеддинг для текста с помощью OpenAI.
        
        :param text: Текст для создания эмбеддинга
        :return: Вектор эмбеддинга или None при ошибке
        """
        try:
            # Ограничиваем длину текста
            if len(text) > 8000:
                text = text[:8000] + "..."
            
            response = await openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания эмбеддинга: {e}")
            return None
    
    async def add_user_memory(self, user_id: int, content: str, memory_type: str = "dialogue", metadata: Dict = None):
        """
        Добавляет новую память пользователя в векторную базу.
        
        :param user_id: ID пользователя
        :param content: Содержимое памяти
        :param memory_type: Тип памяти (dialogue, preference, fact, etc.)
        :param metadata: Дополнительные метаданные
        """
        if not self.collection:
            logger.warning("Векторная БД недоступна")
            return
        
        try:
            # Создаем эмбеддинг
            embedding = await self.create_embedding(content)
            if not embedding:
                return
            
            # Подготавливаем метаданные
            doc_metadata = {
                "user_id": user_id,
                "memory_type": memory_type,
                "timestamp": str(asyncio.get_event_loop().time()),
                **(metadata or {})
            }
            
            # Создаем уникальный ID для документа
            doc_id = hashlib.md5(f"{user_id}_{content}_{memory_type}".encode()).hexdigest()
            
            # Выполняем добавление в отдельном потоке
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.collection.add(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[content],
                    metadatas=[doc_metadata]
                )
            )
            
            logger.info(f"✅ Добавлена память для пользователя {user_id}: {memory_type}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления памяти: {e}")
    
    async def search_user_memory(self, user_id: int, query: str, limit: int = 5) -> List[Dict]:
        """
        Ищет релевантные воспоминания пользователя.
        
        :param user_id: ID пользователя
        :param query: Поисковый запрос
        :param limit: Максимальное количество результатов
        :return: Список релевантных воспоминаний
        """
        if not self.collection:
            return []
        
        try:
            # Создаем эмбеддинг для запроса
            query_embedding = await self.create_embedding(query)
            if not query_embedding:
                return []
            
            # Выполняем поиск в отдельном потоке
            results = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit,
                    where={"user_id": user_id}
                )
            )
            
            # Форматируем результаты
            memories = []
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    memory = {
                        "content": doc,
                        "score": results['distances'][0][i] if results['distances'] else 1.0,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {}
                    }
                    memories.append(memory)
            
            logger.info(f"🔍 Найдено {len(memories)} воспоминаний для пользователя {user_id}")
            return memories
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска памяти: {e}")
            return []
    
    async def get_user_context(self, user_id: int, current_message: str) -> str:
        """
        Получает персональный контекст пользователя для улучшения ответов.
        
        :param user_id: ID пользователя
        :param current_message: Текущее сообщение пользователя
        :return: Персональный контекст в виде строки
        """
        try:
            # Ищем релевантные воспоминания
            memories = await self.search_user_memory(user_id, current_message, limit=3)
            
            if not memories:
                return ""
            
            # Формируем контекст из найденных воспоминаний
            context_parts = []
            context_parts.append("ПЕРСОНАЛЬНЫЙ КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:")
            
            for memory in memories:
                score = memory['score']
                content = memory['content']
                memory_type = memory['metadata'].get('memory_type', 'unknown')
                
                # Добавляем только релевантные воспоминания (score < 0.3 означает высокую релевантность)
                if score < 0.5:
                    context_parts.append(f"- [{memory_type.upper()}] {content}")
            
            if len(context_parts) > 1:
                context_parts.append("УЧИТЫВАЙ ЭТОТ КОНТЕКСТ ПРИ ОТВЕТЕ.")
                return "\n".join(context_parts)
            
            return ""
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения контекста: {e}")
            return ""
    
    async def add_user_preference(self, user_id: int, preference: str):
        """Добавляет предпочтение пользователя."""
        await self.add_user_memory(
            user_id, 
            preference, 
            "preference",
            {"category": "user_preference"}
        )
    
    async def add_user_fact(self, user_id: int, fact: str):
        """Добавляет факт о пользователе."""
        await self.add_user_memory(
            user_id,
            fact,
            "fact", 
            {"category": "user_fact"}
        )
    
    async def learn_from_dialogue(self, user_id: int, user_message: str, bot_response: str):
        """
        Обучается на основе диалога с пользователем.
        
        :param user_id: ID пользователя
        :param user_message: Сообщение пользователя
        :param bot_response: Ответ бота
        """
        # Добавляем диалог в память
        dialogue_entry = f"Пользователь: {user_message}\nБот: {bot_response}"
        await self.add_user_memory(
            user_id,
            dialogue_entry,
            "dialogue",
            {"interaction_type": "qa_pair"}
        )
        
        # Пытаемся извлечь предпочтения из сообщения пользователя
        preferences = await self._extract_preferences(user_message)
        for pref in preferences:
            await self.add_user_preference(user_id, pref)
    
    async def _extract_preferences(self, message: str) -> List[str]:
        """
        Извлекает предпочтения пользователя из сообщения.
        
        :param message: Сообщение пользователя
        :return: Список извлеченных предпочтений
        """
        try:
            # Используем простую эвристику для извлечения предпочтений
            preference_indicators = [
                "мне нравится", "я люблю", "предпочитаю", "не люблю", 
                "ненавижу", "мой стиль", "я всегда", "я никогда",
                "i like", "i love", "i prefer", "i hate", "i always", "i never"
            ]
            
            preferences = []
            message_lower = message.lower()
            
            for indicator in preference_indicators:
                if indicator in message_lower:
                    # Простое извлечение предпочтения
                    start_idx = message_lower.find(indicator)
                    preference_text = message[start_idx:start_idx + 100]  # Берем до 100 символов
                    preferences.append(f"Предпочтение: {preference_text.strip()}")
            
            return preferences
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения предпочтений: {e}")
            return []
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """
        Получает статистику памяти пользователя.
        
        :param user_id: ID пользователя
        :return: Словарь со статистикой
        """
        if not self.collection:
            return {"total_memories": 0, "by_type": {}}
        
        try:
            # Получаем все записи пользователя
            results = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.collection.get(where={"user_id": user_id})
            )
            
            stats = {
                "total_memories": len(results['ids']) if results['ids'] else 0,
                "by_type": {}
            }
            
            # Подсчитываем по типам
            if results['metadatas']:
                for metadata in results['metadatas']:
                    memory_type = metadata.get('memory_type', 'unknown')
                    stats['by_type'][memory_type] = stats['by_type'].get(memory_type, 0) + 1
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {"total_memories": 0, "by_type": {}}
    
    async def clear_user_memory(self, user_id: int, memory_type: Optional[str] = None):
        """
        Очищает память пользователя.
        
        :param user_id: ID пользователя
        :param memory_type: Тип памяти для удаления (None = все)
        """
        if not self.collection:
            return
        
        try:
            where_clause = {"user_id": user_id}
            if memory_type:
                where_clause["memory_type"] = memory_type
            
            # Получаем ID документов для удаления
            results = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.collection.get(where=where_clause)
            )
            
            if results['ids']:
                # Удаляем документы
                await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    lambda: self.collection.delete(ids=results['ids'])
                )
                
                logger.info(f"🗑️ Очищена память пользователя {user_id}: {len(results['ids'])} записей")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки памяти: {e}")


# Глобальный экземпляр персонального ассистента
personal_assistant = PersonalAssistant()
