"""
Модуль интеграции с Tavily API для поиска актуальной информации в интернете.

Этот модуль предоставляет функции для выполнения поиска через Tavily API,
который специализируется на предоставлении актуальной и релевантной информации
из интернета для AI-систем.
"""

from typing import List, Dict, Optional
import logging
from tavily import TavilyClient
from .config import settings

logger = logging.getLogger(__name__)

class TavilySearchClient:
    """Клиент для работы с Tavily Search API."""
    
    def __init__(self):
        """Инициализация клиента Tavily."""
        self.client = None
        if settings.TAVILY_API_KEY:
            try:
                self.client = TavilyClient(api_key=settings.TAVILY_API_KEY)
                logger.info("Tavily клиент успешно инициализирован")
            except Exception as e:
                logger.error(f"Ошибка инициализации Tavily клиента: {e}")
        else:
            logger.warning("TAVILY_API_KEY не установлен в переменных окружения")
    
    def is_available(self) -> bool:
        """Проверяет, доступен ли Tavily API."""
        return self.client is not None
    
    def search(self, query: str, max_results: int = 5, include_domains: Optional[List[str]] = None, 
                    exclude_domains: Optional[List[str]] = None) -> Optional[Dict]:
        """
        Выполняет поиск через Tavily API (синхронная версия).
        
        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов (по умолчанию 5)
            include_domains: Список доменов для включения в поиск
            exclude_domains: Список доменов для исключения из поиска
            
        Returns:
            Словарь с результатами поиска или None в случае ошибки
        """
        if not self.is_available():
            logger.error("Tavily клиент недоступен")
            return None
        
        try:
            # Параметры поиска
            search_params = {
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",  # Углубленный поиск
                "include_answer": True,      # Включить краткий ответ
                "include_raw_content": False  # Не включать сырой контент (экономия токенов)
            }
            
            # Добавляем фильтры доменов если указаны
            if include_domains:
                search_params["include_domains"] = include_domains
            if exclude_domains:
                search_params["exclude_domains"] = exclude_domains
            
            logger.info(f"Выполняем поиск Tavily: '{query}' (макс. результатов: {max_results})")
            
            # Выполняем поиск
            results = self.client.search(**search_params)
            
            logger.info(f"Получено {len(results.get('results', []))} результатов от Tavily")
            return results
            
        except Exception as e:
            logger.error(f"Ошибка поиска Tavily: {e}")
            return None
    
    def format_search_results(self, results: Dict) -> str:
        """
        Форматирует результаты поиска для отображения пользователю.
        
        Args:
            results: Результаты поиска от Tavily API
            
        Returns:
            Отформатированная строка с результатами
        """
        if not results:
            return "❌ Не удалось получить результаты поиска."
        
        formatted_text = "🔍 **Результаты поиска:**\n\n"
        
        # Добавляем краткий ответ если есть
        if results.get("answer"):
            formatted_text += f"💡 **Краткий ответ:**\n{results['answer']}\n\n"
        
        # Добавляем результаты поиска
        search_results = results.get("results", [])
        if search_results:
            formatted_text += "📋 **Источники:**\n\n"
            for i, result in enumerate(search_results[:5], 1):
                title = result.get("title", "Без названия")
                url = result.get("url", "")
                content = result.get("content", "")
                
                formatted_text += f"{i}. **{title}**\n"
                if content:
                    # Ограничиваем длину описания
                    content_preview = content[:200] + "..." if len(content) > 200 else content
                    formatted_text += f"{content_preview}\n"
                formatted_text += f"🔗 {url}\n\n"
        
        return formatted_text

# Создаем глобальный экземпляр клиента
tavily_client = TavilySearchClient()


async def search_web(query: str, max_results: int = 5) -> str:
    """
    Упрощенная функция поиска в интернете.
    
    Args:
        query: Поисковый запрос
        max_results: Максимальное количество результатов
        
    Returns:
        Отформатированные результаты поиска
    """
    import asyncio
    
    if not tavily_client.is_available():
        return "❌ Поиск в интернете недоступен. Проверьте настройку TAVILY_API_KEY."
    
    # Выполняем синхронный вызов в отдельном потоке
    results = await asyncio.to_thread(tavily_client.search, query, max_results)
    return tavily_client.format_search_results(results)


async def search_news(query: str, max_results: int = 3) -> str:
    """
    Поиск новостей по запросу.
    
    Args:
        query: Поисковый запрос для новостей
        max_results: Максимальное количество результатов
        
    Returns:
        Отформатированные новости
    """
    import asyncio
    
    # Добавляем ключевые слова для поиска новостей
    news_query = f"{query} новости сегодня"
    
    # Включаем новостные домены
    news_domains = [
        "lenta.ru", "ria.ru", "tass.ru", "rbc.ru", "kommersant.ru",
        "bbc.com", "cnn.com", "reuters.com", "news.google.com"
    ]
    
    if not tavily_client.is_available():
        return "❌ Поиск новостей недоступен. Проверьте настройку TAVILY_API_KEY."
    
    results = await asyncio.to_thread(tavily_client.search, news_query, max_results, news_domains)
    formatted_results = tavily_client.format_search_results(results)
    
    # Заменяем заголовок на более подходящий для новостей
    if formatted_results.startswith("🔍 **Результаты поиска:**"):
        formatted_results = formatted_results.replace("🔍 **Результаты поиска:**", "📰 **Последние новости:**")
    
    return formatted_results
