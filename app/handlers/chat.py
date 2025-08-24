"""Chat handler with AI conversation and message history."""

import logging
import time
from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.types import ChatAction

from app.db import db
from app.config import settings
from app.services.openai_service import (
    chat_completion, moderate_content, rate_limiter
)
from app.utils.keyboards import get_main_menu_keyboard
from app.utils.texts import get_usage_limit_text, PLAN_LIMITS

logger = logging.getLogger(__name__)
router = Router(name="chat")


async def check_usage_limits(user_id: int, action: str) -> bool:
    """Check if user is within usage limits."""
    user = await db.get_user(user_id)
    plan = user['plan'] if user else 'FREE'
    
    # Get current usage
    used = await db.get_daily_usage(user_id, action)
    
    # Get limits for plan
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['FREE'])
    limit_key = f"{action}s" if action != 'voice' else action
    limit = limits.get(limit_key, 0)
    
    return used < limit


async def split_long_message(text: str, max_length: int = 4000) -> list:
    """Split long message into chunks."""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        
        # Find last space before max_length
        split_point = text.rfind(' ', 0, max_length)
        if split_point == -1:
            split_point = max_length
        
        chunks.append(text[:split_point])
        text = text[split_point:].lstrip()
    
    return chunks


@router.message()
async def handle_text_message(message: types.Message):
    """Handle text messages for AI chat."""
    try:
        user_id = message.from_user.id
        text = message.text.strip()
        
        # Skip if message starts with known commands or contains callback data
        if (text.startswith('/') or 
            text.startswith('wiki ') or 
            text.startswith('погода ') or 
            text.startswith('calc ') or
            text.startswith('напомни ') or
            text.startswith('сгенерируй ') or
            text.startswith('создай ') or
            'callback_data' in text.lower()):
            return
        
        # Check rate limiting
        if not await rate_limiter.is_allowed(user_id):
            await message.answer("⏱ Слишком много запросов. Попробуйте через минуту.")
            return
        
        # Check usage limits
        if not await check_usage_limits(user_id, 'message'):
            user = await db.get_user(user_id)
            plan = user['plan'] if user else 'FREE'
            limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['FREE'])
            used = await db.get_daily_usage(user_id, 'message')
            
            await message.answer(
                get_usage_limit_text('сообщения', used, limits['messages']),
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Show typing indicator
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        start_time = time.time()
        
        # Moderate content
        is_flagged, reason = await moderate_content(text)
        if is_flagged:
            await message.answer(
                "😔 Извините, я не могу обработать это сообщение из-за политики безопасности. "
                "Пожалуйста, попробуйте переформулировать запрос.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed moderation
            await db.log_usage(
                user_id, 'chat', 
                int((time.time() - start_time) * 1000),
                'moderation_failed',
                {'reason': reason}
            )
            return
        
        # Get user session for persona
        session = await db.get_user_session(user_id)
        persona = session.get('persona', 'default')
        
        # Add user message to history
        await db.add_message(user_id, 'user', text)
        
        # Get recent message history
        recent_messages = await db.get_recent_messages(user_id)
        
        # Prepare messages for OpenAI (exclude system messages)
        openai_messages = []
        for msg in recent_messages:
            if msg['role'] in ['user', 'assistant']:
                openai_messages.append({
                    'role': msg['role'],
                    'content': msg['content']
                })
        
        # Generate AI response
        try:
            ai_response = await chat_completion(
                openai_messages, 
                persona=persona,
                user_id=user_id
            )
            
            # Add AI response to history
            await db.add_message(user_id, 'assistant', ai_response)
            
            # Split long response
            response_chunks = await split_long_message(ai_response)
            
            # Send response(s)
            for i, chunk in enumerate(response_chunks):
                if i > 0:
                    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
                
                if i == len(response_chunks) - 1:
                    # Add menu to last message
                    await message.answer(chunk, reply_markup=get_main_menu_keyboard())
                else:
                    await message.answer(chunk)
            
            # Log successful usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'chat', duration_ms, 'success',
                {'persona': persona, 'response_length': len(ai_response)}
            )
            
        except Exception as e:
            logger.error(f"AI chat error: {e}")
            await message.answer(
                "😔 Произошла ошибка при обработке запроса. Попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'chat', duration_ms, 'error',
                {'error': str(e)}
            )
    
    except Exception as e:
        logger.error(f"Chat handler error: {e}")
        await message.answer(
            "😔 Произошла неожиданная ошибка. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )