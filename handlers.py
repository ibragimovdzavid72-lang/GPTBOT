from aiogram import Router, F
from aiogram.types import Message
from openai_api import ask_gpt, generate_image

router = Router()

@router.message(F.text)
async def handle_text(msg: Message):
    reply = ask_gpt([{"role": "user", "content": msg.text}])
    await msg.answer(reply)

@router.message(F.photo)
async def handle_photo(msg: Message):
    await msg.answer("📷 Фото принято. Пока поддержка фото в разработке.")

@router.message(F.voice)
async def handle_voice(msg: Message):
    await msg.answer("🎙 Голосовое сообщение принято. Пока поддержка STT в разработке.")
