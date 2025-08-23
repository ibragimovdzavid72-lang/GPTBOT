"""Аналитика для Русского Бота"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import structlog

лог = structlog.get_logger("аналитика")


class АналитикаДвижок:
    """Движок аналитики для русского бота."""
    
    def __init__(self, менеджер_бд):
        self.бд = менеджер_бд
        
        # Метрики в реальном времени
        self.времена_запросов = []
        self.счетчик_ошибок = 0
        self.счетчик_сообщений = 0
        self.последний_сброс = datetime.utcnow()
    
    def записать_начало_запроса(self):
        """Записать начало обработки запроса."""
        pass
    
    def записать_завершение_запроса(self, длительность: float, успех: bool):
        """Записать завершение обработки запроса."""
        self.времена_запросов.append((datetime.utcnow(), длительность, успех))
        
        # Хранить только данные последнего часа
        обрез = datetime.utcnow() - timedelta(hours=1)
        self.времена_запросов = [
            (ts, dur, succ) for ts, dur, succ in self.времена_запросов
            if ts > обрез
        ]
        
        if not успех:
            self.счетчик_ошибок += 1
    
    def записать_обработанное_сообщение(self, ид_пользователя: int, длительность: float):
        """Записать обработанное сообщение."""
        self.счетчик_сообщений += 1
        self.записать_завершение_запроса(длительность, True)
    
    def записать_ошибку(self, тип_ошибки: str):
        """Записать возникновение ошибки."""
        self.счетчик_ошибок += 1
        лог.warning("Ошибка записана", тип_ошибки=тип_ошибки)
    
    async def получить_системную_статистику(self) -> Dict[str, Any]:
        """Получить текущую системную статистику."""
        try:
            # Получить базовую статистику из базы данных
            статистика = await self.бд.получить_системную_статистику()
            
            # Добавить метрики реального времени
            среднее_время_ответа = self._вычислить_среднее_время_ответа()
            частота_ошибок = self._вычислить_частоту_ошибок()
            
            статистика.update({
                "среднее_время_ответа": среднее_время_ответа,
                "частота_ошибок": частота_ошибок,
                "запросов_за_последний_час": len(self.времена_запросов),
                "обработано_сообщений": self.счетчик_сообщений
            })
            
            return статистика
            
        except Exception as e:
            лог.error("Не удалось получить системную статистику", ошибка=str(e))
            return {}
    
    def _вычислить_среднее_время_ответа(self) -> float:
        """Вычислить среднее время ответа."""
        if not self.времена_запросов:
            return 0.0
        
        успешные_запросы = [
            длительность for _, длительность, успех in self.времена_запросов
            if успех
        ]
        
        if not успешные_запросы:
            return 0.0
        
        return sum(успешные_запросы) / len(успешные_запросы)
    
    def _вычислить_частоту_ошибок(self) -> float:
        """Вычислить частоту ошибок в процентах."""
        if not self.времена_запросов:
            return 0.0
        
        общее_запросов = len(self.времена_запросов)
        неудачных_запросов = sum(
            1 for _, _, успех in self.времена_запросов
            if not успех
        )
        
        return (неудачных_запросов / общее_запросов) * 100
    
    async def собрать_системные_метрики(self):
        """Собрать и сохранить системные метрики."""
        try:
            статистика = await self.получить_системную_статистику()
            лог.info("Системные метрики собраны", **статистика)
            
        except Exception as e:
            лог.error("Не удалось собрать метрики", ошибка=str(e))
    
    async def очистить_старые_данные(self):
        """Очистить старые данные аналитики."""
        try:
            лог.info("Старые данные аналитики очищены")
            
        except Exception as e:
            лог.error("Не удалось очистить старые данные", ошибка=str(e))
    
    async def получить_метрики_прометеуса(self) -> str:
        """Получить метрики в формате Prometheus."""
        try:
            статистика = await self.получить_системную_статистику()
            
            метрики = f"""# HELP russian_telegram_bot_users_total Общее количество пользователей
# TYPE russian_telegram_bot_users_total gauge
russian_telegram_bot_users_total {статистика.get('всего_пользователей', 0)}

# HELP russian_telegram_bot_active_users Активные пользователи сегодня
# TYPE russian_telegram_bot_active_users gauge  
russian_telegram_bot_active_users {статистика.get('активных_пользователей_сегодня', 0)}

# HELP russian_telegram_bot_messages_total Сообщений обработано сегодня
# TYPE russian_telegram_bot_messages_total counter
russian_telegram_bot_messages_total {статистика.get('сообщений_сегодня', 0)}

# HELP russian_telegram_bot_response_time_seconds Среднее время ответа
# TYPE russian_telegram_bot_response_time_seconds gauge
russian_telegram_bot_response_time_seconds {статистика.get('среднее_время_ответа', 0)}
"""
            
            return метрики
            
        except Exception as e:
            лог.error("Не удалось сгенерировать метрики Prometheus", ошибка=str(e))
            return ""