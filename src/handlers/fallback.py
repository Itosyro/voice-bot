"""Catch-all для неподдерживаемых типов сообщений.

Регистрируется ПОСЛЕДНИМ роутером: всё, что не поймали voice/text/командные
хендлеры (фото, документы, стикеры, локации…), раньше тонуло в тишине —
человек не понимал, видит ли его бот вообще.
"""

from aiogram import Router
from aiogram.types import Message

from src.ui.keyboards import mode_keyboard

router = Router()

UNSUPPORTED_INPUT = (
    "🤷 Такой формат я пока не понимаю.\n\n"
    "Я умею: <b>голосовые</b>, <b>аудио</b>, <b>видео-кружки</b>, "
    "<b>видео</b> и <b>текст</b>.\n"
    "Файлы, фото и стикеры — пока нет."
)


@router.message()
async def handle_unsupported(message: Message) -> None:
    await message.answer(UNSUPPORTED_INPUT, reply_markup=mode_keyboard(), parse_mode="HTML")
