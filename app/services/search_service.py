"""
Search service using Tavily API.
Выделенный сервис для работы с поиском в интернете.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from ..config import settings
from ..constants import (
    MAX_SEARCH_RESULTS, MAX_NEWS_RESULTS, MAX_CONTENT_PREVIEW_LENGTH,
    NEWS_DOMAINS, ERROR_MESSAGES, HEADERS
)

logger = logging.getLogger(__name__)


class SearchService:
    """Сервис для работы с Tavily API поиском."""
    
    def __init__(self):
        """Инициализация сервиса поиска."""
        self.client: Optional[object] = None
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Инициализация Tavily клиента."""
        try:
            from tavily import TavilyClient
            if settings.TAVILY_API_KEY:
                self.client = TavilyClient(api_key=settings.TAVILY_API_KEY)
                logger.info("Tavily client successfully initialized")
            else:
                logger.warning("TAVILY_API_KEY not set")
        except ImportError:
            logger.warning("Tavily client not available. Install tavily-python for search functionality.")
    
    def is_available(self) -> bool:
        """Проверяет доступность поискового сервиса."""
        return self.client is not None
    
    async def search_web(self, query: str, max_results: int = MAX_SEARCH_RESULTS) -> str:
        """Выполняет поиск в интернете."""
        if not self.is_available():
            return ERROR_MESSAGES["search_unavailable"]
        
        try:
            search_params = {
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_answer": True,
                "include_raw_content": False
            }
            
            results = await asyncio.to_thread(self.client.search, **search_params)
            return self._format_search_results(results)
        except Exception as e:
            logger.error(f"Search error: {e}")
            return ERROR_MESSAGES["search_error"]
    
    async def search_news(self, query: str, max_results: int = MAX_NEWS_RESULTS) -> str:
        """Выполняет поиск новостей."""
        if not self.is_available():
            return ERROR_MESSAGES["news_unavailable"]
        
        try:
            news_query = f"{query} новости сегодня"
            search_params = {
                "query": news_query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_answer": True,
                "include_raw_content": False,
                "include_domains": NEWS_DOMAINS
            }
            
            results = await asyncio.to_thread(self.client.search, **search_params)
            formatted_results = self._format_search_results(results)
            
            # Заменяем заголовок для новостей
            if formatted_results.startswith(HEADERS["search_results"]):
                formatted_results = formatted_results.replace(
                    HEADERS["search_results"], 
                    HEADERS["news_results"]
                )
            
            return formatted_results
        except Exception as e:
            logger.error(f"News search error: {e}")
            return ERROR_MESSAGES["news_error"]
    
    def _format_search_results(self, results: Dict) -> str:
        """Форматирует результаты поиска."""
        if not results:
            return ERROR_MESSAGES["no_results"]
        
        formatted_text = f"{HEADERS['search_results']}\n\n"
        
        # Добавляем краткий ответ если есть
        if results.get("answer"):
            formatted_text += f"{HEADERS['brief_answer']}\n{results['answer']}\n\n"
        
        # Добавляем результаты поиска
        search_results = results.get("results", [])
        if search_results:
            formatted_text += f"{HEADERS['sources']}\n\n"
            for i, result in enumerate(search_results[:5], 1):
                title = result.get("title", "Без названия")
                url = result.get("url", "")
                content = result.get("content", "")
                
                formatted_text += f"{i}. **{title}**\n"
                if content:
                    content_preview = (
                        content[:MAX_CONTENT_PREVIEW_LENGTH] + "..." 
                        if len(content) > MAX_CONTENT_PREVIEW_LENGTH 
                        else content
                    )
                    formatted_text += f"{content_preview}\n"
                formatted_text += f"🔗 {url}\n\n"
        
        return formatted_text
    
    def detect_search_intent(self, text: str, search_keywords: List[str]) -> bool:
        """Определяет намерение поиска в тексте."""
        text_lower = text.lower()
        return (
            any(keyword in text_lower for keyword in search_keywords) 
            and len(text) > 20
        )


# Глобальный экземпляр сервиса
search_service = SearchService()