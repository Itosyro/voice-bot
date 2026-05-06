from aiogram.fsm.state import State, StatesGroup


class ModeSelection(StatesGroup):
    waiting_for_mode = State()
    waiting_for_style = State()
    waiting_for_lang = State()
    waiting_for_input = State()
