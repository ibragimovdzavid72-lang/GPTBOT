"""Voice handler for speech recognition and synthesis."""

import logging
import time
from aiogram import Router, types
from aiogram.types import ChatAction, BufferedInputFile

from app.db import db
from app.services.openai_service import (
    transcribe_audio, text_to_speech, chat_completion,
    moderate_content, rate_limiter
)
from app.utils.keyboards import get_main_menu_keyboard
from app.utils.texts import get_usage_limit_text, PLAN_LIMITS

logger = logging.getLogger(__name__)
router = Router(name="voice")


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


@router.message(lambda message: message.voice)
async def handle_voice_message(message: types.Message):
    """Handle voice messages with STT -> AI -> TTS pipeline."""
    try:
        user_id = message.from_user.id
        
        # Check rate limiting
        if not await rate_limiter.is_allowed(user_id):
            await message.answer("⏱ Слишком много запросов. Попробуйте через минуту.")
            return
        
        # Check usage limits
        if not await check_usage_limits(user_id, 'voice'):
            user = await db.get_user(user_id)
            plan = user['plan'] if user else 'FREE'
            limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['FREE'])
            used = await db.get_daily_usage(user_id, 'voice')
            
            await message.answer(
                get_usage_limit_text('голосовые сообщения', used, limits['voice']),
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Show typing indicator
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        start_time = time.time()
        
        try:
            # Download voice file
            voice_file = await message.bot.get_file(message.voice.file_id)
            voice_data = await message.bot.download_file(voice_file.file_path)
            voice_bytes = voice_data.read()
            
            logger.info(f"Processing voice message from user {user_id}, size: {len(voice_bytes)} bytes")
            
            # Step 1: Speech to Text
            transcribed_text = await transcribe_audio(voice_bytes)
            logger.info(f"Transcribed text: {transcribed_text[:100]}...")
            
            if not transcribed_text.strip():
                await message.answer(
                    "😔 Не удалось распознать речь. Попробуйте говорить четче.",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Step 2: Moderate content
            is_flagged, reason = await moderate_content(transcribed_text)
            if is_flagged:
                await message.answer(
                    "😔 Извините, я не могу обработать это сообщение из-за политики безопасности.",
                    reply_markup=get_main_menu_keyboard()
                )
                
                # Log failed moderation
                await db.log_usage(
                    user_id, 'voice', 
                    int((time.time() - start_time) * 1000),
                    'moderation_failed',
                    {'reason': reason, 'transcribed': transcribed_text}
                )
                return
            
            # Step 3: Add to message history and get AI response
            await db.add_message(user_id, 'user', transcribed_text, 'voice')
            
            # Get user session for persona
            session = await db.get_user_session(user_id)
            persona = session.get('persona', 'default')
            
            # Get recent message history
            recent_messages = await db.get_recent_messages(user_id)
            
            # Prepare messages for OpenAI
            openai_messages = []
            for msg in recent_messages:
                if msg['role'] in ['user', 'assistant']:
                    openai_messages.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })
            
            # Generate AI response (shorter for voice)
            system_prompt_addition = " Отвечай кратко и по делу, максимум 2-3 предложения для голосового ответа."
            
            ai_response = await chat_completion(
                openai_messages, 
                persona=persona,
                user_id=user_id
            )
            
            # Limit response length for TTS
            if len(ai_response) > 500:
                ai_response = ai_response[:500] + "..."
            
            logger.info(f"AI response: {ai_response[:100]}...")
            
            # Step 4: Add AI response to history
            await db.add_message(user_id, 'assistant', ai_response, 'voice')
            
            # Show upload voice indicator
            await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VOICE)
            
            # Step 5: Text to Speech
            voice_response = await text_to_speech(ai_response, voice="alloy")
            
            # Send voice response
            voice_file = BufferedInputFile(voice_response, filename="response.mp3")
            await message.answer_voice(
                voice_file,
                caption=f"🔊 <b>Распознано:</b> {transcribed_text[:100]}..." if len(transcribed_text) > 100 else f"🔊 <b>Распознано:</b> {transcribed_text}",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log successful usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'voice', duration_ms, 'success',
                {
                    'transcribed': transcribed_text,
                    'response': ai_response,
                    'persona': persona,
                    'voice_duration': message.voice.duration
                }
            )
            
        except Exception as e:
            logger.error(f"Voice processing error: {e}")
            await message.answer(
                "😔 Произошла ошибка при обработке голосового сообщения. Попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'voice', duration_ms, 'error',
                {'error': str(e)}
            )
    
    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await message.answer(
            "😔 Произошла неожиданная ошибка. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )