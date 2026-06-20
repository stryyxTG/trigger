from aiogram.fsm.state import State, StatesGroup


class AccountConnect(StatesGroup):
    phone = State()
    code = State()
    password = State()


class TriggerCreate(StatesGroup):
    text = State()
    match_type = State()
    response = State()


class TriggerChatAdd(StatesGroup):
    chat_id = State()


class SettingsEdit(StatesGroup):
    cooldown = State()
