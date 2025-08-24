"""Admin handler for management commands and analytics."""

import logging
from aiogram import Router, types
from aiogram.filters import Command

from app.db import db
from app.config import settings
from app.utils.keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router(name="admin")


async def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    if user_id == settings.super_admin_id:
        return True
    
    user = await db.get_user(user_id)
    return user and user.get('is_admin', False)


async def is_super_admin(user_id: int) -> bool:
    """Check if user is super admin."""
    return user_id == settings.super_admin_id


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Handle /stats command - show platform statistics."""
    try:
        user_id = message.from_user.id
        
        if not await is_admin(user_id):
            await message.answer(
                "❌ У вас нет прав администратора.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Get platform statistics
        stats = await db.get_stats()
        
        response = "📊 <b>Статистика платформы</b>\n\n"
        
        # User statistics
        response += f"👥 <b>Пользователи:</b> {stats['total_users']}\n"
        
        plan_dist = stats.get('plan_distribution', {})
        response += f"🆓 FREE: {plan_dist.get('FREE', 0)}\n"
        response += f"⭐ PRO: {plan_dist.get('PRO', 0)}\n"
        response += f"👥 TEAM: {plan_dist.get('TEAM', 0)}\n\n"
        
        # Today's usage
        usage = stats.get('today_usage', {})
        response += f"📈 <b>Использование сегодня:</b>\n"
        response += f"💬 Чат: {usage.get('chat', 0)}\n"
        response += f"🎨 Изображения: {usage.get('image_generation', 0) + usage.get('image_analysis', 0) + usage.get('image_editing', 0)}\n"
        response += f"🔊 Голос: {usage.get('voice', 0)}\n"
        response += f"📖 Википедия: {usage.get('wikipedia', 0)}\n"
        response += f"🌤 Погода: {usage.get('weather', 0)}\n"
        response += f"🧮 Калькулятор: {usage.get('calculator', 0)}\n"
        response += f"⏰ Напоминания: {usage.get('reminder_created', 0)}\n\n"
        
        # Revenue
        monthly_revenue = stats.get('monthly_revenue_rub', 0)
        response += f"💰 <b>Доход в этом месяце:</b> {monthly_revenue}₽\n"
        
        await message.answer(response, reply_markup=get_main_menu_keyboard())
        
    except Exception as e:
        logger.error(f"Stats command error: {e}")
        await message.answer(
            "😔 Произошла ошибка при получении статистики.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(Command("makeadmin"))
async def cmd_make_admin(message: types.Message):
    """Handle /makeadmin command - make user admin."""
    try:
        user_id = message.from_user.id
        
        if not await is_super_admin(user_id):
            await message.answer(
                "❌ Только супер-администратор может назначать администраторов.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Extract target user ID
        args = message.text.split()
        if len(args) != 2:
            await message.answer(
                "📝 Использование: <code>/makeadmin [user_id]</code>\n"
                "Пример: <code>/makeadmin 123456789</code>",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        try:
            target_user_id = int(args[1])
        except ValueError:
            await message.answer(
                "❌ Неверный ID пользователя. Используйте числовой ID.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Check if user exists
        target_user = await db.get_user(target_user_id)
        if not target_user:
            await message.answer(
                f"❌ Пользователь с ID {target_user_id} не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Make admin
        await db.set_admin(target_user_id, True)
        
        target_name = target_user.get('first_name') or target_user.get('username') or f"ID {target_user_id}"
        
        await message.answer(
            f"✅ Пользователь {target_name} (ID: {target_user_id}) назначен администратором.",
            reply_markup=get_main_menu_keyboard()
        )
        
        # Log admin action
        await db.log_usage(
            user_id, 'admin_assigned', None, 'success',
            {'target_user_id': target_user_id, 'target_name': target_name}
        )
        
        logger.info(f"User {target_user_id} made admin by super admin {user_id}")
        
    except Exception as e:
        logger.error(f"Make admin command error: {e}")
        await message.answer(
            "😔 Произошла ошибка при назначении администратора.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(Command("revokeadmin"))
async def cmd_revoke_admin(message: types.Message):
    """Handle /revokeadmin command - revoke admin rights."""
    try:
        user_id = message.from_user.id
        
        if not await is_super_admin(user_id):
            await message.answer(
                "❌ Только супер-администратор может отзывать права администратора.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Extract target user ID
        args = message.text.split()
        if len(args) != 2:
            await message.answer(
                "📝 Использование: <code>/revokeadmin [user_id]</code>\n"
                "Пример: <code>/revokeadmin 123456789</code>",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        try:
            target_user_id = int(args[1])
        except ValueError:
            await message.answer(
                "❌ Неверный ID пользователя. Используйте числовой ID.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Cannot revoke super admin
        if target_user_id == settings.super_admin_id:
            await message.answer(
                "❌ Нельзя отозвать права у супер-администратора.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Check if user exists
        target_user = await db.get_user(target_user_id)
        if not target_user:
            await message.answer(
                f"❌ Пользователь с ID {target_user_id} не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Revoke admin rights
        await db.set_admin(target_user_id, False)
        
        target_name = target_user.get('first_name') or target_user.get('username') or f"ID {target_user_id}"
        
        await message.answer(
            f"✅ У пользователя {target_name} (ID: {target_user_id}) отозваны права администратора.",
            reply_markup=get_main_menu_keyboard()
        )
        
        # Log admin action
        await db.log_usage(
            user_id, 'admin_revoked', None, 'success',
            {'target_user_id': target_user_id, 'target_name': target_name}
        )
        
        logger.info(f"Admin rights revoked for user {target_user_id} by super admin {user_id}")
        
    except Exception as e:
        logger.error(f"Revoke admin command error: {e}")
        await message.answer(
            "😔 Произошла ошибка при отзыве прав администратора.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    """Handle /broadcast command - send message to all users."""
    try:
        user_id = message.from_user.id
        
        if not await is_super_admin(user_id):
            await message.answer(
                "❌ Только супер-администратор может отправлять рассылки.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Extract broadcast message
        text = message.text[10:].strip()  # Remove "/broadcast "
        
        if not text:
            await message.answer(
                "📝 Использование: <code>/broadcast [сообщение]</code>\n"
                "Пример: <code>/broadcast Важное обновление бота!</code>",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # This is a simplified version - in production you'd want to:
        # 1. Get all user IDs from database
        # 2. Send messages in batches with delays
        # 3. Handle failed deliveries
        # 4. Show progress to admin
        
        await message.answer(
            f"📢 <b>Рассылка запущена</b>\n\n"
            f"Сообщение: {text}\n\n"
            f"⚠️ Функция рассылки требует дополнительной реализации для безопасной отправки всем пользователям.",
            reply_markup=get_main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Broadcast command error: {e}")
        await message.answer(
            "😔 Произошла ошибка при запуске рассылки.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(Command("mode"))
async def cmd_mode(message: types.Message):
    """Handle /mode command - quick persona change."""
    try:
        from app.utils.keyboards import get_persona_keyboard
        from app.utils.texts import PERSONA_DESCRIPTIONS
        
        user_id = message.from_user.id
        
        # Get current persona
        session = await db.get_user_session(user_id)
        current_persona = session.get('persona', 'default')
        
        text = f"👤 <b>Смена персоны ИИ</b>\n\n"
        text += f"Текущая: {PERSONA_DESCRIPTIONS[current_persona]}\n\n"
        text += "Выберите стиль общения:"
        
        await message.answer(text, reply_markup=get_persona_keyboard())
        
    except Exception as e:
        logger.error(f"Mode command error: {e}")
        await message.answer(
            "😔 Произошла ошибка при смене режима.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(Command("lang"))
async def cmd_lang(message: types.Message):
    """Handle /lang command - quick language change."""
    try:
        from app.utils.keyboards import get_language_keyboard
        from app.utils.texts import LANGUAGE_NAMES
        
        user_id = message.from_user.id
        
        # Get current language
        session = await db.get_user_session(user_id)
        current_lang = session.get('language', 'ru')
        
        text = f"🌐 <b>Смена языка</b>\n\n"
        text += f"Текущий: {LANGUAGE_NAMES[current_lang]}\n\n"
        text += "Выберите язык интерфейса:"
        
        await message.answer(text, reply_markup=get_language_keyboard())
        
    except Exception as e:
        logger.error(f"Lang command error: {e}")
        await message.answer(
            "😔 Произошла ошибка при смене языка.",
            reply_markup=get_main_menu_keyboard()
        )