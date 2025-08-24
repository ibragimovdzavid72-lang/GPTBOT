"""Keyboard utilities for inline keyboards."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get main menu inline keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 Чат", callback_data="menu:chat"),
            InlineKeyboardButton(text="🎨 Изображение", callback_data="menu:image")
        ],
        [
            InlineKeyboardButton(text="🔊 Голос", callback_data="menu:voice"),
            InlineKeyboardButton(text="🛠 Инструменты", callback_data="menu:tools")
        ],
        [
            InlineKeyboardButton(text="⏰ Напоминание", callback_data="menu:reminder"),
            InlineKeyboardButton(text="💳 Тариф", callback_data="menu:plan")
        ],
        [
            InlineKeyboardButton(text="👤 Персона", callback_data="menu:persona"),
            InlineKeyboardButton(text="🌐 Язык", callback_data="menu:language")
        ]
    ])
    return keyboard


def get_persona_keyboard() -> InlineKeyboardMarkup:
    """Get persona selection keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤖 Обычный", callback_data="persona:default"),
            InlineKeyboardButton(text="🤖 Робот", callback_data="persona:robot")
        ],
        [
            InlineKeyboardButton(text="👂 Слушатель", callback_data="persona:listener"),
            InlineKeyboardButton(text="🤓 Умник", callback_data="persona:nerd")
        ],
        [
            InlineKeyboardButton(text="😏 Циник", callback_data="persona:cynic")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="back:main")
        ]
    ])
    return keyboard


def get_language_keyboard() -> InlineKeyboardMarkup:
    """Get language selection keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="back:main")
        ]
    ])
    return keyboard


def get_tools_keyboard() -> InlineKeyboardMarkup:
    """Get tools selection keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📖 Википедия", callback_data="tool:wiki"),
            InlineKeyboardButton(text="🌤 Погода", callback_data="tool:weather")
        ],
        [
            InlineKeyboardButton(text="🧮 Калькулятор", callback_data="tool:calc"),
            InlineKeyboardButton(text="🔄 Переводчик", callback_data="tool:translate")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="back:main")
        ]
    ])
    return keyboard


def get_plan_keyboard(current_plan: str = "FREE") -> InlineKeyboardMarkup:
    """Get subscription plan keyboard."""
    buttons = []
    
    if current_plan != "PRO":
        buttons.append([
            InlineKeyboardButton(text="⭐ PRO - 199₽/мес", callback_data="buy:pro")
        ])
    
    if current_plan != "TEAM":
        buttons.append([
            InlineKeyboardButton(text="👥 TEAM - 799₽/мес", callback_data="buy:team")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back:main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_confirmation_keyboard(action: str) -> InlineKeyboardMarkup:
    """Get confirmation keyboard."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm:{action}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="back:main")
        ]
    ])
    return keyboard