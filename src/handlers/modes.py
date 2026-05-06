from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.ui.keyboards import mode_keyboard
from src.ui.messages import CHOOSE_MODE

router = Router()


@router.message(Command("modes"))
async def cmd_modes(message: Message) -> None:
    await message.answer(CHOOSE_MODE, reply_markup=mode_keyboard(), parse_mode="HTML")
