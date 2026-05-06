from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.ui.keyboards import mode_keyboard

router = Router()


@router.message(Command("modes"))
async def cmd_modes(message: Message) -> None:
    await message.answer("Выбери режим:", reply_markup=mode_keyboard())
