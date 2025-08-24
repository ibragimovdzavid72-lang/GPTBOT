"""Payments handler for Telegram payments and subscriptions."""

import logging
from datetime import datetime, timedelta
from aiogram import Router, types
from aiogram.filters import Command, Text
from aiogram.types import LabeledPrice, PreCheckoutQuery

from app.db import db
from app.config import settings
from app.utils.keyboards import get_main_menu_keyboard, get_plan_keyboard
from app.utils.texts import get_plan_info_text

logger = logging.getLogger(__name__)
router = Router(name="payments")


@router.message(Command("buy"))
async def cmd_buy(message: types.Message):
    """Handle /buy command - show subscription plans."""
    try:
        user = await db.get_user(message.from_user.id)
        current_plan = user['plan'] if user else 'FREE'
        
        text = "💳 <b>Тарифные планы</b>\n\n"
        
        # FREE plan info
        text += f"🆓 <b>FREE</b> (текущий)\n" if current_plan == 'FREE' else "🆓 <b>FREE</b>\n"
        text += f"💬 Сообщения: {settings.free_daily_messages}/день\n"
        text += f"🎨 Изображения: {settings.free_daily_images}/день\n"
        text += f"🔊 Голос: {settings.free_daily_voice}/день\n\n"
        
        # PRO plan info
        text += f"⭐ <b>PRO</b> (текущий)\n" if current_plan == 'PRO' else "⭐ <b>PRO</b>\n"
        text += f"💬 Сообщения: {settings.pro_daily_messages}/день\n"
        text += f"🎨 Изображения: {settings.pro_daily_images}/день\n"
        text += f"🔊 Голос: {settings.pro_daily_voice}/день\n"
        text += f"💰 Стоимость: {settings.pro_price_rub}₽/месяц\n\n"
        
        # TEAM plan info
        text += f"👥 <b>TEAM</b> (текущий)\n" if current_plan == 'TEAM' else "👥 <b>TEAM</b>\n"
        text += f"💬 Сообщения: {settings.team_daily_messages}/день\n"
        text += f"🎨 Изображения: {settings.team_daily_images}/день\n"
        text += f"🔊 Голос: {settings.team_daily_voice}/день\n"
        text += f"💰 Стоимость: {settings.team_price_rub}₽/месяц\n\n"
        
        if current_plan != 'FREE':
            plan_expires = user.get('plan_expires_at')
            if plan_expires:
                expires_str = plan_expires.strftime("%d.%m.%Y")
                text += f"📅 Ваша подписка действует до: {expires_str}\n\n"
        
        text += "Выберите план для покупки:"
        
        await message.answer(text, reply_markup=get_plan_keyboard(current_plan))
        
    except Exception as e:
        logger.error(f"Buy command error: {e}")
        await message.answer(
            "😔 Произошла ошибка при загрузке тарифов. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )


@router.callback_query(Text(startswith="buy:"))
async def handle_buy_callbacks(callback_query: types.CallbackQuery):
    """Handle buy button callbacks."""
    try:
        plan = callback_query.data.split(":", 1)[1].upper()
        user_id = callback_query.from_user.id
        
        if not settings.payment_provider_token:
            await callback_query.message.edit_text(
                "😔 Извините, платежи временно недоступны. "
                "Свяжитесь с администратором.",
                reply_markup=get_main_menu_keyboard()
            )
            await callback_query.answer()
            return
        
        # Check current plan
        user = await db.get_user(user_id)
        current_plan = user['plan'] if user else 'FREE'
        
        if current_plan == plan:
            await callback_query.answer("У вас уже есть этот план!", show_alert=True)
            return
        
        # Determine price and description
        if plan == 'PRO':
            price = settings.pro_price_rub
            title = "Подписка PRO"
            description = f"Подписка PRO на 30 дней. {settings.pro_daily_messages} сообщений, {settings.pro_daily_images} изображений, {settings.pro_daily_voice} голосовых в день."
        elif plan == 'TEAM':
            price = settings.team_price_rub
            title = "Подписка TEAM"
            description = f"Подписка TEAM на 30 дней. {settings.team_daily_messages} сообщений, {settings.team_daily_images} изображений, {settings.team_daily_voice} голосовых в день."
        else:
            await callback_query.answer("Неизвестный план!", show_alert=True)
            return
        
        # Create payment record
        payment_id = await db.create_payment(user_id, plan, price)
        
        # Create invoice
        prices = [LabeledPrice(label=title, amount=price * 100)]  # Amount in kopecks
        
        await callback_query.message.answer_invoice(
            title=title,
            description=description,
            payload=f"plan_{plan.lower()}_{payment_id}",
            provider_token=settings.payment_provider_token,
            currency="RUB",
            prices=prices,
            start_parameter=f"buy_{plan.lower()}",
            photo_url="https://via.placeholder.com/512x512.png?text=AI+Bot",
            photo_size=512,
            photo_width=512,
            photo_height=512,
            need_email=False,
            need_phone_number=False,
            need_shipping_address=False,
            send_phone_number_to_provider=False,
            send_email_to_provider=False,
            is_flexible=False,
            protect_content=False
        )
        
        await callback_query.message.edit_text(
            f"💳 Счет на оплату создан!\n\n"
            f"📦 План: {plan}\n"
            f"💰 Сумма: {price}₽\n\n"
            f"Нажмите кнопку 'Pay' для оплаты.",
            reply_markup=get_main_menu_keyboard()
        )
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Buy callback error: {e}")
        await callback_query.answer("Произошла ошибка при создании счета", show_alert=True)


@router.pre_checkout_query()
async def handle_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """Handle pre-checkout query."""
    try:
        payload = pre_checkout_query.invoice_payload
        
        # Validate payload format
        if not payload.startswith("plan_"):
            await pre_checkout_query.answer(ok=False, error_message="Недействительный счет")
            return
        
        # Extract plan and payment_id from payload
        try:
            parts = payload.split("_")
            plan = parts[1].upper()
            payment_id = int(parts[2])
        except (IndexError, ValueError):
            await pre_checkout_query.answer(ok=False, error_message="Недействительный формат счета")
            return
        
        # Verify payment exists
        # Note: We should ideally check the payment in database here
        
        # Verify plan and amount
        expected_amount = 0
        if plan == 'PRO':
            expected_amount = settings.pro_price_rub * 100
        elif plan == 'TEAM':
            expected_amount = settings.team_price_rub * 100
        
        if pre_checkout_query.total_amount != expected_amount:
            await pre_checkout_query.answer(ok=False, error_message="Неверная сумма платежа")
            return
        
        # Approve the payment
        await pre_checkout_query.answer(ok=True)
        
        logger.info(f"Pre-checkout approved for user {pre_checkout_query.from_user.id}, plan {plan}")
        
    except Exception as e:
        logger.error(f"Pre-checkout error: {e}")
        await pre_checkout_query.answer(ok=False, error_message="Ошибка обработки платежа")


@router.message(lambda message: message.successful_payment)
async def handle_successful_payment(message: types.Message):
    """Handle successful payment."""
    try:
        payment = message.successful_payment
        user_id = message.from_user.id
        
        # Extract plan and payment_id from payload
        payload = payment.invoice_payload
        parts = payload.split("_")
        plan = parts[1].upper()
        payment_id = int(parts[2])
        
        # Update payment record
        await db.update_payment(
            payment_id,
            payment.telegram_payment_charge_id,
            payment.provider_payment_charge_id,
            'completed'
        )
        
        # Calculate expiration date (30 days from now)
        expires_at = datetime.now() + timedelta(days=30)
        
        # Upgrade user plan
        await db.upgrade_user_plan(user_id, plan, expires_at)
        
        # Send confirmation
        expires_str = expires_at.strftime("%d.%m.%Y")
        
        response = f"✅ <b>Оплата успешна!</b>\n\n"
        response += f"📦 План: <b>{plan}</b>\n"
        response += f"💰 Сумма: {payment.total_amount // 100}₽\n"
        response += f"📅 Действует до: {expires_str}\n"
        response += f"🆔 ID транзакции: {payment.telegram_payment_charge_id}\n\n"
        response += f"Теперь у вас доступны расширенные лимиты!"
        
        await message.answer(response, reply_markup=get_main_menu_keyboard())
        
        # Log successful payment
        await db.log_usage(
            user_id, 'payment_completed', None, 'success',
            {
                'plan': plan,
                'amount': payment.total_amount // 100,
                'telegram_charge_id': payment.telegram_payment_charge_id,
                'provider_charge_id': payment.provider_payment_charge_id,
                'expires_at': expires_at.isoformat()
            }
        )
        
        logger.info(f"Payment completed for user {user_id}: {plan} plan, {payment.total_amount // 100}₽")
        
    except Exception as e:
        logger.error(f"Successful payment error: {e}")
        await message.answer(
            "✅ Платеж прошел успешно, но произошла ошибка при активации подписки. "
            "Свяжитесь с поддержкой.",
            reply_markup=get_main_menu_keyboard()
        )