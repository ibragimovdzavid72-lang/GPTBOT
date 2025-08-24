"""Tools handler for Wikipedia, weather, calculator, and other utilities."""

import logging
import time
import re
import ast
import operator
from aiogram import Router, types
from aiogram.filters import Text
from aiogram.types import ChatAction

from app.db import db
from app.utils.keyboards import get_main_menu_keyboard
from app.services.openai_service import rate_limiter

logger = logging.getLogger(__name__)
router = Router(name="tools")


# Safe operators for calculator
safe_operators = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expression: str) -> float:
    """Safely evaluate mathematical expression."""
    try:
        node = ast.parse(expression, mode='eval')
        return _eval_node(node.body)
    except Exception:
        raise ValueError("Invalid mathematical expression")


def _eval_node(node):
    """Recursively evaluate AST node."""
    if isinstance(node, ast.Constant):  # Python 3.8+
        return node.value
    elif isinstance(node, ast.Num):  # Python < 3.8
        return node.n
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op = safe_operators.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op)}")
        return op(left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        op = safe_operators.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op)}")
        return op(operand)
    else:
        raise ValueError(f"Unsupported node type: {type(node)}")


@router.message(Text(startswith="wiki "))
async def handle_wikipedia(message: types.Message):
    """Handle Wikipedia search."""
    try:
        user_id = message.from_user.id
        query = message.text[5:].strip()
        
        if not query:
            await message.answer(
                "📖 Введите запрос для поиска в Википедии:\n"
                "Например: <code>wiki Эйнштейн</code>",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Check rate limiting
        if not await rate_limiter.is_allowed(user_id):
            await message.answer("⏱ Слишком много запросов. Попробуйте через минуту.")
            return
        
        # Show typing indicator
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        start_time = time.time()
        
        try:
            import wikipedia
            
            # Set language to Russian
            wikipedia.set_lang("ru")
            
            # Search for the query
            search_results = wikipedia.search(query, results=5)
            
            if not search_results:
                await message.answer(
                    f"📖 Ничего не найдено по запросу: <b>{query}</b>",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Get the first result
            page_title = search_results[0]
            page = wikipedia.page(page_title)
            
            # Get summary (first 2 sentences)
            summary = wikipedia.summary(page_title, sentences=3)
            
            # Format response
            response = f"📖 <b>{page.title}</b>\n\n{summary}\n\n🔗 <a href='{page.url}'>Читать полностью</a>"
            
            # Limit response length
            if len(response) > 4000:
                response = response[:3900] + "...\n\n🔗 <a href='" + page.url + "'>Читать полностью</a>"
            
            await message.answer(response, reply_markup=get_main_menu_keyboard())
            
            # Log successful usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'wikipedia', duration_ms, 'success',
                {'query': query, 'page_title': page.title, 'url': page.url}
            )
            
        except wikipedia.exceptions.DisambiguationError as e:
            # Multiple pages found
            options = e.options[:5]  # Show first 5 options
            response = f"📖 Найдено несколько статей по запросу <b>{query}</b>:\n\n"
            for i, option in enumerate(options, 1):
                response += f"{i}. {option}\n"
            response += f"\nУточните запрос или выберите один из вариантов."
            
            await message.answer(response, reply_markup=get_main_menu_keyboard())
            
        except wikipedia.exceptions.PageError:
            await message.answer(
                f"📖 Страница не найдена: <b>{query}</b>",
                reply_markup=get_main_menu_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")
            await message.answer(
                "😔 Произошла ошибка при поиске в Википедии. Попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'wikipedia', duration_ms, 'error',
                {'error': str(e), 'query': query}
            )
    
    except Exception as e:
        logger.error(f"Wikipedia handler error: {e}")
        await message.answer(
            "😔 Произошла неожиданная ошибка. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(Text(startswith="погода "))
async def handle_weather(message: types.Message):
    """Handle weather requests."""
    try:
        user_id = message.from_user.id
        city = message.text[7:].strip()
        
        if not city:
            await message.answer(
                "🌤 Введите название города:\n"
                "Например: <code>погода Москва</code>",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Check rate limiting
        if not await rate_limiter.is_allowed(user_id):
            await message.answer("⏱ Слишком много запросов. Попробуйте через минуту.")
            return
        
        # Show typing indicator
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        start_time = time.time()
        
        try:
            import httpx
            
            # First, get coordinates using geocoding API
            geocoding_url = f"https://geocoding-api.open-meteo.com/v1/search"
            
            async with httpx.AsyncClient() as client:
                geo_response = await client.get(
                    geocoding_url,
                    params={"name": city, "count": 1, "language": "ru", "format": "json"}
                )
                geo_response.raise_for_status()
                geo_data = geo_response.json()
            
            if not geo_data.get("results"):
                await message.answer(
                    f"🌤 Город не найден: <b>{city}</b>",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            location = geo_data["results"][0]
            lat, lon = location["latitude"], location["longitude"]
            city_name = location["name"]
            country = location.get("country", "")
            
            # Get weather data
            weather_url = "https://api.open-meteo.com/v1/forecast"
            
            async with httpx.AsyncClient() as client:
                weather_response = await client.get(
                    weather_url,
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                        "timezone": "auto",
                        "forecast_days": 3
                    }
                )
                weather_response.raise_for_status()
                weather_data = weather_response.json()
            
            current = weather_data["current"]
            daily = weather_data["daily"]
            
            # Weather code to description mapping
            weather_codes = {
                0: "☀️ Ясно",
                1: "🌤 Малооблачно", 2: "⛅ Переменная облачность", 3: "☁️ Облачно",
                45: "🌫 Туман", 48: "🌫 Изморозь",
                51: "🌦 Легкая морось", 53: "🌦 Морось", 55: "🌧 Сильная морось",
                61: "🌧 Легкий дождь", 63: "🌧 Дождь", 65: "🌧 Сильный дождь",
                71: "❄️ Легкий снег", 73: "❄️ Снег", 75: "❄️ Сильный снег",
                95: "⛈ Гроза", 96: "⛈ Гроза с градом", 99: "⛈ Сильная гроза"
            }
            
            current_weather = weather_codes.get(current["weather_code"], "🌈 Неизвестно")
            
            # Format response
            response = f"🌤 <b>Погода в {city_name}"
            if country:
                response += f", {country}"
            response += f"</b>\n\n"
            
            response += f"<b>Сейчас:</b>\n"
            response += f"🌡 Температура: {current['temperature_2m']}°C\n"
            response += f"💧 Влажность: {current['relative_humidity_2m']}%\n"
            response += f"💨 Ветер: {current['wind_speed_10m']} км/ч\n"
            response += f"☁️ Состояние: {current_weather}\n\n"
            
            response += f"<b>Прогноз на 3 дня:</b>\n"
            
            for i in range(3):
                date_str = daily["time"][i]
                max_temp = daily["temperature_2m_max"][i]
                min_temp = daily["temperature_2m_min"][i]
                weather_code = daily["weather_code"][i]
                weather_desc = weather_codes.get(weather_code, "🌈")
                
                # Format date
                from datetime import datetime
                date_obj = datetime.fromisoformat(date_str)
                date_formatted = date_obj.strftime("%d.%m")
                
                response += f"📅 {date_formatted}: {weather_desc} {min_temp}°...{max_temp}°C\n"
            
            await message.answer(response, reply_markup=get_main_menu_keyboard())
            
            # Log successful usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'weather', duration_ms, 'success',
                {'city': city, 'found_city': city_name, 'country': country}
            )
            
        except Exception as e:
            logger.error(f"Weather API error: {e}")
            await message.answer(
                "😔 Произошла ошибка при получении прогноза погоды. Попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'weather', duration_ms, 'error',
                {'error': str(e), 'city': city}
            )
    
    except Exception as e:
        logger.error(f"Weather handler error: {e}")
        await message.answer(
            "😔 Произошла неожиданная ошибка. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(Text(startswith="calc "))
async def handle_calculator(message: types.Message):
    """Handle calculator requests."""
    try:
        user_id = message.from_user.id
        expression = message.text[5:].strip()
        
        if not expression:
            await message.answer(
                "🧮 Введите математическое выражение:\n"
                "Например: <code>calc 2+2*3</code>\n"
                "Поддерживаются: +, -, *, /, %, ** (степень)",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Check rate limiting
        if not await rate_limiter.is_allowed(user_id):
            await message.answer("⏱ Слишком много запросов. Попробуйте через минуту.")
            return
        
        start_time = time.time()
        
        try:
            # Clean expression (remove spaces, replace some common symbols)
            clean_expr = expression.replace(" ", "").replace("×", "*").replace("÷", "/")
            
            # Validate expression contains only allowed characters
            allowed_chars = set("0123456789+-*/.%()")
            if not all(c in allowed_chars for c in clean_expr):
                await message.answer(
                    "🧮 Недопустимые символы в выражении.\n"
                    "Используйте только цифры и операторы: +, -, *, /, %, ()",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Calculate result
            result = safe_eval(clean_expr)
            
            # Format result
            if isinstance(result, float):
                if result.is_integer():
                    result = int(result)
                else:
                    result = round(result, 8)  # Limit decimal places
            
            response = f"🧮 <b>Калькулятор</b>\n\n<code>{expression}</code> = <b>{result}</b>"
            
            await message.answer(response, reply_markup=get_main_menu_keyboard())
            
            # Log successful usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'calculator', duration_ms, 'success',
                {'expression': expression, 'result': str(result)}
            )
            
        except ValueError as e:
            await message.answer(
                f"🧮 Ошибка в выражении: {expression}\n"
                "Проверьте синтаксис и попробуйте снова.",
                reply_markup=get_main_menu_keyboard()
            )
            
        except ZeroDivisionError:
            await message.answer(
                "🧮 Ошибка: деление на ноль!",
                reply_markup=get_main_menu_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Calculator error: {e}")
            await message.answer(
                "🧮 Произошла ошибка при вычислении. Проверьте выражение.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'calculator', duration_ms, 'error',
                {'error': str(e), 'expression': expression}
            )
    
    except Exception as e:
        logger.error(f"Calculator handler error: {e}")
        await message.answer(
            "😔 Произошла неожиданная ошибка. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(Text(startswith=["переведи ", "translate "]))
async def handle_translator(message: types.Message):
    """Handle translation requests using AI."""
    try:
        user_id = message.from_user.id
        
        # Extract text to translate
        if message.text.startswith("переведи "):
            text_to_translate = message.text[9:].strip()
        else:  # translate
            text_to_translate = message.text[10:].strip()
        
        if not text_to_translate:
            await message.answer(
                "🔄 Введите текст для перевода:\n"
                "Например: <code>переведи hello world</code>",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Check rate limiting
        if not await rate_limiter.is_allowed(user_id):
            await message.answer("⏱ Слишком много запросов. Попробуйте через минуту.")
            return
        
        # Show typing indicator
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        start_time = time.time()
        
        try:
            from app.services.openai_service import chat_completion
            
            # Create translation prompt
            prompt = f"Переведи этот текст на русский язык (если он не на русском) или на английский (если он на русском). Просто верни перевод без дополнительных комментариев: {text_to_translate}"
            
            messages = [{"role": "user", "content": prompt}]
            
            translation = await chat_completion(messages, persona='default', user_id=user_id)
            
            response = f"🔄 <b>Перевод:</b>\n\n<b>Исходный текст:</b> {text_to_translate}\n\n<b>Перевод:</b> {translation}"
            
            await message.answer(response, reply_markup=get_main_menu_keyboard())
            
            # Log successful usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'translation', duration_ms, 'success',
                {'original': text_to_translate, 'translation': translation}
            )
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            await message.answer(
                "😔 Произошла ошибка при переводе. Попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'translation', duration_ms, 'error',
                {'error': str(e), 'text': text_to_translate}
            )
    
    except Exception as e:
        logger.error(f"Translation handler error: {e}")
        await message.answer(
            "😔 Произошла неожиданная ошибка. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )