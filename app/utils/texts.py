"""Text utilities and message templates."""

from app.db import db
from app.config import settings

WELCOME_TEXT = """
🤖 <b>Добро пожаловать в AI Bot!</b>

Привет, {name}! Я ваш умный помощник с искусственным интеллектом.

<b>Что я умею:</b>
💬 Вести умные разговоры с памятью
🎨 Создавать и анализировать изображения
🔊 Работать с голосовыми сообщениями
🛠 Пользоваться инструментами (Википедия, погода, калькулятор)
⏰ Устанавливать напоминания
💳 Предлагать различные тарифы

{stats}

Используйте кнопки меню ниже для быстрого доступа к функциям!
"""

PERSONA_DESCRIPTIONS = {
    'default': '🤖 Обычный: Дружелюбный и полезный помощник',
    'robot': '🤖 Робот: Технический и точный ответы',
    'listener': '👂 Слушатель: Эмпатичный и понимающий',
    'nerd': '🤓 Умник: Детальный и научный подход',
    'cynic': '😏 Циник: Критический и саркастичный стиль'
}

LANGUAGE_NAMES = {
    'ru': '🇷🇺 Русский',
    'en': '🇬🇧 English'
}

PLAN_LIMITS = {
    'FREE': {
        'messages': settings.free_daily_messages,
        'images': settings.free_daily_images,
        'voice': settings.free_daily_voice,
        'name': 'FREE'
    },
    'PRO': {
        'messages': settings.pro_daily_messages,
        'images': settings.pro_daily_images,
        'voice': settings.pro_daily_voice,
        'name': 'PRO'
    },
    'TEAM': {
        'messages': settings.team_daily_messages,
        'images': settings.team_daily_images,
        'voice': settings.team_daily_voice,
        'name': 'TEAM'
    }
}


async def get_user_stats_text(user_id: int) -> str:
    """Get user's daily statistics text."""
    try:
        user = await db.get_user(user_id)
        plan = user['plan'] if user else 'FREE'
        
        # Get today's usage
        messages_used = await db.get_daily_usage(user_id, 'chat')
        images_used = await db.get_daily_usage(user_id, 'image')
        voice_used = await db.get_daily_usage(user_id, 'voice')
        
        # Get limits for current plan
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['FREE'])
        
        stats = f"""
<b>📊 Статистика на сегодня:</b>
💬 Сообщения: {messages_used}/{limits['messages']}
🎨 Изображения: {images_used}/{limits['images']}
🔊 Голос: {voice_used}/{limits['voice']}

💎 Ваш тариф: <b>{limits['name']}</b>
"""
        return stats
        
    except Exception:
        return "\n📊 <b>Статистика временно недоступна</b>"


def get_plan_info_text(plan: str) -> str:
    """Get plan information text."""
    if plan == 'FREE':
        return f"""
💎 <b>Тариф FREE</b>

<b>Ваши лимиты:</b>
💬 Сообщения: {settings.free_daily_messages}/день
🎨 Изображения: {settings.free_daily_images}/день
🔊 Голос: {settings.free_daily_voice}/день

Хотите больше возможностей? Обновитесь до PRO или TEAM!
"""
    elif plan == 'PRO':
        return f"""
⭐ <b>Тариф PRO</b>

<b>Ваши лимиты:</b>
💬 Сообщения: {settings.pro_daily_messages}/день
🎨 Изображения: {settings.pro_daily_images}/день  
🔊 Голос: {settings.pro_daily_voice}/день

<b>Стоимость:</b> {settings.pro_price_rub}₽/месяц
"""
    elif plan == 'TEAM':
        return f"""
👥 <b>Тариф TEAM</b>

<b>Ваши лимиты:</b>
💬 Сообщения: {settings.team_daily_messages}/день
🎨 Изображения: {settings.team_daily_images}/день
🔊 Голос: {settings.team_daily_voice}/день

<b>Стоимость:</b> {settings.team_price_rub}₽/месяц
"""
    
    return "Неизвестный тариф"


def get_menu_help_text(menu_type: str) -> str:
    """Get help text for menu options."""
    help_texts = {
        'chat': """
💬 <b>Режим чата</b>

Просто напишите любое сообщение, и я отвечу с помощью ИИ.
Я запоминаю контекст разговора для более естественного общения.

<b>Примеры:</b>
• "Расскажи о квантовой физике"
• "Помоги написать письмо"
• "Что думаешь о современном искусстве?"
""",
        'image': """
🎨 <b>Режим изображений</b>

<b>Что я умею:</b>
• <b>Анализ</b>: Отправьте фото, и я его опишу
• <b>Генерация</b>: Напишите "сгенерируй [описание]"
• <b>Редактирование</b>: Ответьте на фото с текстом "измени [как]"

<b>Примеры:</b>
• "сгенерируй закат над океаном"
• "создай логотип для кафе"
• [фото] "измени цвет на синий"
""",
        'voice': """
🔊 <b>Режим голоса</b>

Отправьте голосовое сообщение, и я:
1. Распознаю речь (Speech-to-Text)
2. Обработаю запрос с помощью ИИ
3. Отвечу голосом (Text-to-Speech)

Говорите четко и не слишком быстро для лучшего распознавания.
""",
        'tools': """
🛠 <b>Инструменты</b>

<b>Доступные команды:</b>
• <b>wiki [запрос]</b> - Поиск в Википедии
• <b>погода [город]</b> - Прогноз погоды
• <b>calc [выражение]</b> - Калькулятор

<b>Примеры:</b>
• "wiki Эйнштейн"
• "погода Москва"
• "calc 15*8+42"
""",
        'reminder': """
⏰ <b>Напоминания</b>

Установите напоминание на определенное время.

<b>Формат:</b>
"напомни [текст] в [ДД.ММ ЧЧ:ММ]"

<b>Примеры:</b>
• "напомни купить молоко в 15.12 18:00"
• "напомни позвонить маме в 25.12 10:30"
• "напомни встреча через час"
""",
        'plan': """
💳 <b>Тарифные планы</b>

<b>FREE</b> - Базовый функционал
<b>PRO (199₽/мес)</b> - Больше лимитов
<b>TEAM (799₽/мес)</b> - Максимальные возможности

Выберите подходящий план ниже.
"""
    }
    
    return help_texts.get(menu_type, "Информация недоступна")


def get_usage_limit_text(action: str, used: int, limit: int) -> str:
    """Get usage limit warning text."""
    return f"""
⚠️ <b>Лимит исчерпан</b>

Вы использовали все {action} на сегодня ({used}/{limit}).

💎 Обновитесь до PRO или TEAM для больших лимитов!
Используйте /buy для просмотра тарифов.
"""


SYSTEM_PROMPTS = {
    'default': "Ты дружелюбный и полезный AI-помощник. Отвечай кратко и по делу на русском языке.",
    'robot': "Ты технический AI-робот. Отвечай точно, формально и структурированно. Избегай эмоций.",
    'listener': "Ты эмпатичный слушатель и психолог. Проявляй понимание, поддержку и давай мудрые советы.",
    'nerd': "Ты эрудированный ученый. Давай детальные, научно обоснованные ответы с фактами и объяснениями.",
    'cynic': "Ты критически мыслящий циник. Отвечай с долей скептицизма и сарказма, но остается полезным."
}