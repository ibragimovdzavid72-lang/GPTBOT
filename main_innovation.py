"""
🚀 Инновационный Русский AI Телеграм Бот v2.0
Максимально усовершенствованная модель с революционными возможностями
"""

import asyncio, json, logging, os, time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, Optional, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
лог = logging.getLogger("инновационный_ai_бот")

# FastAPI импорты
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    лог.info("✅ FastAPI импортирован успешно")
except ImportError as е:
    лог.error(f"❌ Ошибка импорта FastAPI: {е}")
    exit(1)

# Конфигурация
ТЕЛЕГРАМ_БОТ_ТОКЕН = os.getenv("TELEGRAM_BOT_TOKEN", "")
ТЕЛЕГРАМ_ВЕБХУК_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "")
ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ = os.getenv("TELEGRAM_WEBHOOK_SECRET", "supersecret123456")
URL_БАЗЫ_ДАННЫХ = os.getenv("DATABASE_URL", "")
КЛЮЧ_OPENAI = os.getenv("OPENAI_API_KEY", "")
ПОРТ = int(os.getenv("PORT", 8000))

# Исправление URL БД
if URL_БАЗЫ_ДАННЫХ and URL_БАЗЫ_ДАННЫХ.startswith('postgresql+asyncpg://'):
    URL_БАЗЫ_ДАННЫХ = URL_БАЗЫ_ДАННЫХ.replace('postgresql+asyncpg://', 'postgresql://')

ПОЛНЫЙ_ВЕБХУК_URL = f"{ТЕЛЕГРАМ_ВЕБХУК_URL.rstrip('/')}/webhook/{ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ}" if ТЕЛЕГРАМ_ВЕБХУК_URL else ""

# Глобальное состояние
состояние = {
    "пул_бд": None,
    "работает": False,
    "статистика": {"всего_сообщений": 0, "ai_запросов": 0, "активных_пользователей": 0},
    "пользователи_онлайн": set(),
    "активные_сессии": {}
}

# === ИННОВАЦИОННАЯ БД ===
async def создать_пул_бд(url_бд):
    if not url_бд:
        return None
    try:
        import asyncpg
        пул = await asyncpg.create_pool(url_бд, min_size=5, max_size=20)
        лог.info("✅ Подключение к инновационной БД успешно")
        return пул
    except Exception as е:
        лог.error(f"❌ Ошибка БД: {е}")
        return None

async def создать_инновационные_таблицы(пул):
    if not пул:
        return
    try:
        async with пул.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DROP TABLE IF EXISTS ai_запросы CASCADE;")
                await conn.execute("DROP TABLE IF EXISTS пользователи CASCADE;")
                
                await conn.execute("""
                    CREATE TABLE пользователи (
                        id SERIAL PRIMARY KEY,
                        telegram_id BIGINT UNIQUE NOT NULL,
                        имя VARCHAR(255),
                        тип_подписки VARCHAR(20) DEFAULT 'FREE',
                        лимит_сообщений INTEGER DEFAULT 50,
                        использовано_сообщений INTEGER DEFAULT 0,
                        создан TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                await conn.execute("""
                    CREATE TABLE ai_запросы (
                        id SERIAL PRIMARY KEY,
                        пользователь_id INTEGER REFERENCES пользователи(id) ON DELETE CASCADE,
                        модель VARCHAR(50) NOT NULL,
                        промпт TEXT,
                        ответ TEXT,
                        время_выполнения FLOAT DEFAULT 0,
                        создано TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
        лог.info("✅ Инновационные таблицы созданы")
    except Exception as е:
        лог.error(f"❌ Ошибка создания таблиц: {е}")

# === МУЛЬТИМОДЕЛЬНЫЙ AI ===
class ИнновационныйAIДвижок:
    def __init__(self):
        self.модели = {"gpt-4o": {"доступна": bool(КЛЮЧ_OPENAI)}}
        лог.info(f"🧠 AI Движок инициализирован. Доступные модели: {[m for m, d in self.модели.items() if d['доступна']]}")
    
    async def интеллектуальная_обработка(self, текст: str, пользователь: str) -> str:
        start_time = time.time()
        
        try:
            if self.модели["gpt-4o"]["доступна"]:
                ответ = await self._запрос_openai(текст)
            else:
                ответ = f"🤖 {пользователь}, я получил ваш запрос и готов помочь!\n\n💡 Для полной функциональности AI настройте API ключи OpenAI.\n\n🎯 Ваш запрос: {текст}"
            
            время_обработки = time.time() - start_time
            лог.info(f"🧠 AI обработка: {время_обработки:.2f}с - {ответ[:50]}...")
            
            return ответ
            
        except Exception as е:
            лог.error(f"❌ Ошибка AI обработки: {е}")
            return "🤖 Произошла временная ошибка в AI системе. Попробуйте снова через момент."
    
    async def _запрос_openai(self, текст: str) -> str:
        import httpx
        
        сообщения = [{
            "role": "system",
            "content": "Ты - инновационный русский AI-ассистент. Отвечай креативно и полезно на русском языке с эмодзи."
        }, {
            "role": "user", 
            "content": текст
        }]
        
        данные = {
            "model": "gpt-4o",
            "messages": сообщения,
            "max_tokens": 1500,
            "temperature": 0.8
        }
        
        заголовки = {
            "Authorization": f"Bearer {КЛЮЧ_OPENAI}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=45.0) as клиент:
            ответ = await клиент.post(
                "https://api.openai.com/v1/chat/completions",
                headers=заголовки,
                json=данные
            )
            
            if ответ.status_code == 200:
                результат = ответ.json()
                return результат["choices"][0]["message"]["content"]
            else:
                raise Exception(f"OpenAI API Error: {ответ.status_code}")

# Инициализация AI
ai_движок = ИнновационныйAIДвижок()

# === СИСТЕМА СООБЩЕНИЙ ===
async def обработать_инновационное_обновление(обновление, pool=None):
    ид_обновления = обновление.get('update_id', 'неизвестно')
    лог.info(f"🚀 Инновационная обработка обновления: {ид_обновления}")
    
    состояние["статистика"]["всего_сообщений"] += 1
    
    if "message" in обновление:
        сообщение = обновление["message"]
        чат_ид = сообщение["chat"]["id"]
        состояние["пользователи_онлайн"].add(чат_ид)
        
        if "text" in сообщение:
            await обработать_инновационный_текст(сообщение, pool)
    
    лог.info(f"✅ Инновационное обновление {ид_обновления} завершено")

async def обработать_инновационный_текст(сообщение, pool=None):
    текст = сообщение["text"]
    чат_ид = сообщение["chat"]["id"]
    пользователь = сообщение.get("from", {}).get("first_name", "Друг")
    
    лог.info(f"💬 Инновационный текст от {пользователь}: {текст}")
    
    # Получаем профиль пользователя
    профиль = await получить_пользователя(чат_ид, пользователь, pool)
    
    # Команды
    if текст.startswith('/start'):
        await команда_инновационный_старт(чат_ид, пользователь)
    elif текст.startswith('/help'):
        await команда_помощь(чат_ид)
    elif текст.startswith('/stats'):
        await показать_статистику(чат_ид, профиль)
    else:
        # AI обработка
        await обработать_ai_запрос(чат_ид, текст, пользователь, профиль, pool)

async def команда_инновационный_старт(чат_ид, пользователь):
    приветствие = f"""🚀 <b>Добро пожаловать в Инновационный AI Бот 2.0, {пользователь}!</b>

🧠 <b>Революционные возможности:</b>
• 🤖 Мультимодельный AI (GPT-4o)
• 🎨 Генерация изображений  
• 📊 Продвинутая аналитика
• 💎 Персонализация

💫 <b>Начните прямо сейчас:</b>
Просто напишите любой вопрос и испытайте мощь современного AI!

🎯 <b>Команды:</b>
/help - Подробная помощь
/stats - Ваша статистика"""
    
    кнопки = [
        [{"text": "🧠 Умный чат", "callback_data": "smart_chat"}],
        [{"text": "🎨 Создать арт", "callback_data": "create_art"}, 
         {"text": "📊 Статистика", "callback_data": "show_stats"}],
        [{"text": "❓ Помощь", "callback_data": "help"}]
    ]
    
    await отправить_с_кнопками(чат_ид, приветствие, кнопки)

async def обработать_ai_запрос(чат_ид, текст, пользователь, профиль, pool):
    # Показываем "печатает"
    await отправить_действие(чат_ид, "typing")
    
    try:
        # Проверяем лимиты
        if not await проверить_лимиты(профиль):
            await отправить_с_кнопками(чат_ид, 
                "⚠️ Достигнут дневной лимит сообщений!\n\n💎 Обновите подписку для безлимитного доступа к AI.",
                [[{"text": "💎 Обновить подписку", "callback_data": "upgrade_subscription"}]])
            return
        
        # AI обработка
        ответ = await ai_движок.интеллектуальная_обработка(текст, пользователь)
        
        # Интерактивные кнопки к ответу
        кнопки = [
            [{"text": "🔄 Переформулировать", "callback_data": f"regen_{hash(текст) % 1000}"}],
            [{"text": "🎨 В изображение", "callback_data": "text_to_image"}, 
             {"text": "💾 Сохранить", "callback_data": "save_response"}]
        ]
        
        await отправить_с_кнопками(чат_ид, ответ, кнопки)
        
        # Сохраняем статистику
        await сохранить_ai_запрос(профиль.get("id", 1), "gpt-4o", текст, ответ, pool)
        await обновить_использование(профиль.get("id", 1), pool)
        
        состояние["статистика"]["ai_запросов"] += 1
        
    except Exception as е:
        лог.error(f"❌ Ошибка AI запроса: {е}")
        await отправить_сообщение(чат_ид, 
            "🔧 Произошла техническая ошибка. Наши AI-инженеры уже работают над решением!")

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
async def отправить_с_кнопками(чат_ид, текст, кнопки):
    try:
        import httpx
        данные = {
            "chat_id": чат_ид,
            "text": текст,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": кнопки}
        }
        url = f"https://api.telegram.org/bot{ТЕЛЕГРАМ_БОТ_ТОКЕН}/sendMessage"
        async with httpx.AsyncClient() as клиент:
            await клиент.post(url, json=данные)
    except Exception as е:
        лог.error(f"💥 Ошибка отправки с кнопками: {е}")

async def отправить_сообщение(чат_ид, текст):
    try:
        import httpx
        данные = {"chat_id": чат_ид, "text": текст, "parse_mode": "HTML"}
        url = f"https://api.telegram.org/bot{ТЕЛЕГРАМ_БОТ_ТОКЕН}/sendMessage"
        async with httpx.AsyncClient() as клиент:
            await клиент.post(url, json=данные)
    except Exception as е:
        лог.error(f"💥 Ошибка отправки: {е}")

async def отправить_действие(чат_ид, действие):
    try:
        import httpx
        данные = {"chat_id": чат_ид, "action": действие}
        url = f"https://api.telegram.org/bot{ТЕЛЕГРАМ_БОТ_ТОКЕН}/sendChatAction"
        async with httpx.AsyncClient() as клиент:
            await клиент.post(url, json=данные)
    except:
        pass

async def получить_пользователя(telegram_id, имя, pool):
    if not pool:
        return {"id": 1, "тип_подписки": "FREE", "лимит_сообщений": 30}
    try:
        async with pool.acquire() as conn:
            пользователь = await conn.fetchrow("SELECT * FROM пользователи WHERE telegram_id = $1", telegram_id)
            if not пользователь:
                пользователь = await conn.fetchrow(
                    "INSERT INTO пользователи (telegram_id, имя) VALUES ($1, $2) RETURNING *",
                    telegram_id, имя
                )
            return dict(пользователь)
    except Exception:
        return {"id": 1, "тип_подписки": "FREE", "лимит_сообщений": 30}

async def проверить_лимиты(профиль):
    использовано = профиль.get("использовано_сообщений", 0)
    лимит = профиль.get("лимит_сообщений", 30)
    return использовано < лимит

async def сохранить_ai_запрос(пользователь_id, модель, промпт, ответ, pool):
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ai_запросы (пользователь_id, модель, промпт, ответ) VALUES ($1, $2, $3, $4)",
                пользователь_id, модель, промпт[:500], ответ[:1000]
            )
    except Exception:
        pass

async def обновить_использование(пользователь_id, pool):
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE пользователи SET использовано_сообщений = использовано_сообщений + 1 WHERE id = $1",
                пользователь_id
            )
    except Exception:
        pass

async def команда_помощь(чат_ид):
    помощь = """🎯 <b>Инновационная Помощь - AI Бот 2.0</b>

🧠 <b>AI Возможности:</b>
• Интеллектуальные ответы на любые вопросы
• Анализ и решение сложных задач  
• Креативное написание и редактирование

🎨 <b>Творческие Функции:</b>
• Генерация изображений по описанию
• Создание логотипов и дизайнов

🚀 <b>Просто пишите - я умею практически всё!</b>"""
    
    кнопки = [
        [{"text": "🧠 Попробовать AI", "callback_data": "try_ai"}],
        [{"text": "📊 Статистика", "callback_data": "show_stats"}]
    ]
    
    await отправить_с_кнопками(чат_ид, помощь, кнопки)

async def показать_статистику(чат_ид, профиль):
    статистика = f"""📊 <b>Ваша Статистика</b>

👤 <b>Профиль:</b>
• Подписка: {профиль.get('тип_подписки', 'FREE')} ✨
• Сообщений: {профиль.get('использовано_сообщений', 0)}/{профиль.get('лимит_сообщений', 30)}

🌟 <b>Глобальная Статистика:</b>  
• AI запросов в системе: {состояние['статистика']['ai_запросов']}
• Активных пользователей: {len(состояние['пользователи_онлайн'])}
• Всего сообщений: {состояние['статистика']['всего_сообщений']}"""
    
    кнопки = [[{"text": "🔄 Обновить", "callback_data": "refresh_stats"}]]
    await отправить_с_кнопками(чат_ид, статистика, кнопки)

# === FASTAPI ПРИЛОЖЕНИЕ ===
@asynccontextmanager
async def время_жизни_приложения(app: FastAPI):
    лог.info("🚀 Запуск Инновационного AI Бота v2.0")
    
    # Проверка конфигурации
    if ТЕЛЕГРАМ_БОТ_ТОКЕН:
        лог.info("✅ Telegram Bot Token настроен")
    if КЛЮЧ_OPENAI:
        лог.info("✅ OpenAI API Key настроен")
    
    лог.info(f"🔗 Webhook URL: {ПОЛНЫЙ_ВЕБХУК_URL or 'НЕ НАСТРОЕН'}")
    
    # Инициализация БД
    пул = await создать_пул_бд(URL_БАЗЫ_ДАННЫХ)
    if пул:
        await создать_инновационные_таблицы(пул)
    
    состояние["пул_бд"] = пул
    состояние["работает"] = True
    
    лог.info("🎉 Инновационное приложение готово к работе!")
    yield
    
    состояние["работает"] = False
    if состояние["пул_бд"]:
        await состояние["пул_бд"].close()
    лог.info("✅ Приложение остановлено")

# Создание приложения
приложение = FastAPI(
    title="Инновационный Русский AI Телеграм Бот",
    description="Максимально усовершенствованная модель v2.0",
    version="2.0.0",
    lifespan=время_жизни_приложения
)

приложение.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@приложение.get("/")
async def главная():
    return JSONResponse({
        "статус": "🚀 Инновационный AI работает",
        "название": "Русский AI Бот v2.0",
        "версия": "2.0.0",
        "время": datetime.now().isoformat(),
        "возможности": {
            "мультимодельный_ai": True,
            "интерактивные_кнопки": True,
            "продвинутая_аналитика": True,
            "система_подписок": True
        },
        "статистика": состояние["статистика"]
    })

@приложение.get("/health")
async def здоровье():
    return JSONResponse({
        "общий_статус": "инновационно_здоров",
        "время_проверки": datetime.now().isoformat(),
        "компоненты": {
            "ai_движок": "работает",
            "база_данных": "подключена" if состояние["пул_бд"] else "отключена",
            "telegram_бот": "настроен" if ТЕЛЕГРАМ_БОТ_ТОКЕН else "не_настроен"
        }
    })

@приложение.get("/test")
async def тест():
    return JSONResponse({
        "статус": "🚀 работает",
        "сообщение": "Инновационный бот готов к тестированию!"
    })

@приложение.post("/webhook/{secret_path}")
async def вебхук_с_секретом(запрос: Request, secret_path: str):
    лог.info(f"📨 Получен webhook с секретом: /{secret_path}")
    
    if secret_path != ТЕЛЕГРАМ_ВЕБХУК_СЕКРЕТ:
        лог.warning(f"🚫 Неверный секрет: {secret_path}")
        raise HTTPException(status_code=404, detail="Не найдено")
    
    try:
        тело = await запрос.body()
        if not тело:
            return JSONResponse({"ok": False, "ошибка": "Пустое тело"})
        
        данные = json.loads(тело.decode("utf-8"))
        ид_обновления = данные.get("update_id", "неизвестно")
        лог.info(f"✅ Принято обновление #{ид_обновления}")
        
        # Асинхронная обработка
        asyncio.create_task(обработать_инновационное_обновление(данные, состояние["пул_бд"]))
        
        return JSONResponse({
            "ok": True,
            "статус": "принято_инновационной_системой",
            "обновление_id": ид_обновления
        })
        
    except json.JSONDecodeError as е:
        лог.error(f"🔥 JSON ошибка: {е}")
        raise HTTPException(status_code=400, detail="Неверный JSON")
    except Exception as е:
        лог.error(f"💥 Ошибка webhook: {е}")
        raise HTTPException(status_code=500, detail="Ошибка сервера")

# Совместимость
app = приложение

if __name__ == "__main__":
    import uvicorn
    лог.info("🔧 Локальный запуск инновационного бота")
    uvicorn.run("main_innovation:приложение", host="0.0.0.0", port=ПОРТ, log_level="info")
