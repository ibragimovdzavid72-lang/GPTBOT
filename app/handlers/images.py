"""Images handler for generation, analysis, and editing."""

import logging
import time
import re
from aiogram import Router, types
from aiogram.filters import Text
from aiogram.types import ChatAction, BufferedInputFile
from aiogram.utils.text_decorations import html_decoration as html

from app.db import db
from app.services.openai_service import (
    generate_image, chat_with_image, edit_image, 
    moderate_content, download_image, rate_limiter
)
from app.utils.keyboards import get_main_menu_keyboard
from app.utils.texts import get_usage_limit_text, PLAN_LIMITS

logger = logging.getLogger(__name__)
router = Router(name="images")


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


@router.message(Text(startswith=["сгенерируй", "создай", "нарисуй"]))
async def handle_image_generation(message: types.Message):
    """Handle image generation requests."""
    try:
        user_id = message.from_user.id
        text = message.text.strip()
        
        # Extract prompt
        prompt = re.sub(r'^(сгенерируй|создай|нарисуй)\s+', '', text, flags=re.IGNORECASE)
        
        if not prompt:
            await message.answer(
                "📝 Опишите, что нужно создать:\n"
                "Например: <code>сгенерируй закат над океаном</code>",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Check rate limiting
        if not await rate_limiter.is_allowed(user_id):
            await message.answer("⏱ Слишком много запросов. Попробуйте через минуту.")
            return
        
        # Check usage limits
        if not await check_usage_limits(user_id, 'image'):
            user = await db.get_user(user_id)
            plan = user['plan'] if user else 'FREE'
            limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['FREE'])
            used = await db.get_daily_usage(user_id, 'image')
            
            await message.answer(
                get_usage_limit_text('изображения', used, limits['images']),
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Show upload photo indicator
        await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
        
        start_time = time.time()
        
        # Moderate prompt
        is_flagged, reason = await moderate_content(prompt)
        if is_flagged:
            await message.answer(
                "😔 Извините, я не могу создать изображение с таким описанием. "
                "Пожалуйста, попробуйте другой запрос.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed moderation
            await db.log_usage(
                user_id, 'image_generation', 
                int((time.time() - start_time) * 1000),
                'moderation_failed',
                {'reason': reason, 'prompt': prompt}
            )
            return
        
        try:
            # Generate image
            image_url = await generate_image(prompt)
            
            # Download image
            image_data = await download_image(image_url)
            
            # Send image
            image_file = BufferedInputFile(image_data, filename="generated_image.png")
            await message.answer_photo(
                image_file,
                caption=f"🎨 <b>Создано:</b> {html.quote(prompt)}",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log successful usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'image_generation', duration_ms, 'success',
                {'prompt': prompt, 'image_url': image_url}
            )
            
        except Exception as e:
            logger.error(f"Image generation error: {e}")
            await message.answer(
                "😔 Произошла ошибка при создании изображения. Попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'image_generation', duration_ms, 'error',
                {'error': str(e), 'prompt': prompt}
            )
    
    except Exception as e:
        logger.error(f"Image generation handler error: {e}")
        await message.answer(
            "😔 Произошла неожиданная ошибка. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(lambda message: message.photo)
async def handle_photo_analysis(message: types.Message):
    """Handle photo analysis."""
    try:
        user_id = message.from_user.id
        
        # Check if this is a reply with edit request
        if message.reply_to_message and message.reply_to_message.photo:
            await handle_image_editing(message)
            return
        
        # Check rate limiting
        if not await rate_limiter.is_allowed(user_id):
            await message.answer("⏱ Слишком много запросов. Попробуйте через минуту.")
            return
        
        # Check usage limits
        if not await check_usage_limits(user_id, 'image'):
            user = await db.get_user(user_id)
            plan = user['plan'] if user else 'FREE'
            limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['FREE'])
            used = await db.get_daily_usage(user_id, 'image')
            
            await message.answer(
                get_usage_limit_text('изображения', used, limits['images']),
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Show typing indicator
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        start_time = time.time()
        
        try:
            # Get the largest photo
            photo = message.photo[-1]
            
            # Download photo
            file_info = await message.bot.get_file(photo.file_id)
            image_data = await message.bot.download_file(file_info.file_path)
            image_bytes = image_data.read()
            
            # Get user query or use default
            query = message.caption or "Опиши это изображение подробно"
            
            # Get user session for persona
            session = await db.get_user_session(user_id)
            persona = session.get('persona', 'default')
            
            # Analyze image
            analysis = await chat_with_image(image_bytes, query, persona)
            
            # Send analysis
            await message.answer(
                f"🔍 <b>Анализ изображения:</b>\n\n{analysis}",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log successful usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'image_analysis', duration_ms, 'success',
                {'query': query, 'persona': persona, 'response_length': len(analysis)}
            )
            
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            await message.answer(
                "😔 Произошла ошибка при анализе изображения. Попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'image_analysis', duration_ms, 'error',
                {'error': str(e)}
            )
    
    except Exception as e:
        logger.error(f"Photo analysis handler error: {e}")
        await message.answer(
            "😔 Произошла неожиданная ошибка. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )


async def handle_image_editing(message: types.Message):
    """Handle image editing requests."""
    try:
        user_id = message.from_user.id
        edit_prompt = message.text or message.caption
        
        if not edit_prompt:
            await message.answer(
                "📝 Опишите, как изменить изображение:\n"
                "Например: <code>измени цвет на синий</code>",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Check usage limits
        if not await check_usage_limits(user_id, 'image'):
            user = await db.get_user(user_id)
            plan = user['plan'] if user else 'FREE'
            limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['FREE'])
            used = await db.get_daily_usage(user_id, 'image')
            
            await message.answer(
                get_usage_limit_text('изображения', used, limits['images']),
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Show upload photo indicator
        await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
        
        start_time = time.time()
        
        # Moderate edit prompt
        is_flagged, reason = await moderate_content(edit_prompt)
        if is_flagged:
            await message.answer(
                "😔 Извините, я не могу выполнить такое редактирование. "
                "Пожалуйста, попробуйте другой запрос.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        try:
            # Get original photo
            original_photo = message.reply_to_message.photo[-1]
            file_info = await message.bot.get_file(original_photo.file_id)
            image_data = await message.bot.download_file(file_info.file_path)
            image_bytes = image_data.read()
            
            # Edit image
            edited_image_url = await edit_image(image_bytes, edit_prompt)
            
            # Download edited image
            edited_image_data = await download_image(edited_image_url)
            
            # Send edited image
            image_file = BufferedInputFile(edited_image_data, filename="edited_image.png")
            await message.answer_photo(
                image_file,
                caption=f"✏️ <b>Отредактировано:</b> {html.quote(edit_prompt)}",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log successful usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'image_editing', duration_ms, 'success',
                {'prompt': edit_prompt, 'image_url': edited_image_url}
            )
            
        except Exception as e:
            logger.error(f"Image editing error: {e}")
            await message.answer(
                "😔 Произошла ошибка при редактировании изображения. Попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Log failed usage
            duration_ms = int((time.time() - start_time) * 1000)
            await db.log_usage(
                user_id, 'image_editing', duration_ms, 'error',
                {'error': str(e), 'prompt': edit_prompt}
            )
    
    except Exception as e:
        logger.error(f"Image editing handler error: {e}")
        await message.answer(
            "😔 Произошла неожиданная ошибка. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )