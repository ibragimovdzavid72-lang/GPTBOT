async def handle_update(update: Dict[str, Any]):
    global BOT_ENABLED  # <-- объявляем сразу в начале функции
    try:
        msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
        if not msg:
            return

        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        low = text.casefold()
        is_admin = chat_id in ADMIN_IDS

        # --- Глобальный тумблер ---
        if not BOT_ENABLED and not is_admin:
            await tg_send_message(chat_id, "⏸ Бот на паузе. Обратитесь к администратору.")
            return

        # --- Команды/кнопки ---
        if low in ("/start", "start"):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(
                chat_id,
                "👋 <b>Добро пожаловать в GPTBOT!</b>\n\n"
                "Режимы:\n"
                "• <b>Чат с GPT</b> — отвечаю как ИИ\n"
                "• <b>Создать изображение</b> — рисую по описанию\n\n"
                "Выберите кнопкой ниже или просто напишите сообщение.",
                reply_markup=kb_main(is_admin=is_admin),
            )
            await tg_send_message(chat_id, "Выберите действие:", reply_markup=kb_main(is_admin=is_admin))
            return

        if low in ("ℹ️ помощь", "/help", "help"):
            await tg_send_message(
                chat_id,
                "ℹ️ <b>Справка</b>\n\n"
                "• «💬 Чат с GPT» — текст пойдёт в ИИ\n"
                "• «🎨 Создать изображение» — текст = описание картинки\n"
                "• Команда: <code>/image ваш_описание</code>\n"
                "• Админ: /on /off /admin",
            )
            return

        # ----- Админ-панель -----
        if low in ("/admin", "🛠 админ-панель"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Доступ только для администратора.")
                return
            status = "🟢 ВКЛЮЧЕН" if BOT_ENABLED else "🔴 ВЫКЛЮЧЕН"
            await tg_send_message(
                chat_id,
                f"🛠 <b>Админ-панель</b>\nСтатус бота: {status}\nКоманды: /on, /off",
                reply_markup=kb_admin(),
            )
            return

        if low in ("/on", "🟢 включить бот", "включить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Только админ может включать бота.")
                return
            BOT_ENABLED = True
            await tg_send_message(chat_id, "✅ Бот включён.", reply_markup=kb_admin())
            return

        if low in ("/off", "🔴 выключить бот", "выключить бота"):
            if not is_admin:
                await tg_send_message(chat_id, "🚫 Только админ может выключать бота.")
                return
            BOT_ENABLED = False
            await tg_send_message(chat_id, "⏸ Бот выключен для пользователей.", reply_markup=kb_admin())
            return

        if low in ("⬅️ назад",):
            await tg_send_message(chat_id, "Возвращаемся в меню.", reply_markup=kb_main(is_admin=is_admin))
            return

        # ----- Переключатели режимов -----
        if low in ("💬 чат с gpt",):
            CHAT_MODES[chat_id] = "chat"
            await tg_send_message(chat_id, "🗣 Режим: <b>Чат с GPT</b>. Пишите вопрос — отвечу как ИИ.")
            return

        if low in ("🎨 создать изображение",):
            CHAT_MODES[chat_id] = "image"
            await tg_send_message(chat_id, "🖼 Режим: <b>Изображение</b>. Опишите, что нарисовать.")
            return

        # ----- /image одноразовая -----
        if low.startswith("/image"):
            prompt = text[len("/image"):].strip()
            if not prompt:
                await tg_send_message(
                    chat_id,
                    "📸 Формат: <code>/image красивый закат над морем</code>\n"
                    "Или включите режим «🎨 Создать изображение» и просто напишите описание.",
                )
                return
            await do_image(chat_id, prompt)
            return

        # ----- Режимы -----
        mode = CHAT_MODES.get(chat_id, "chat")
        if mode == "image":
            await do_image(chat_id, text)
            return

        await do_chat(chat_id, text)

    except Exception:
        log.exception("handle update error")
