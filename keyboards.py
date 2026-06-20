from __future__ import annotations

import random

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Trigger, TriggerChat


MATCH_LABELS = {
    "contains": "Содержит",
    "exact": "Точное совпадение",
    "starts": "Начинается с",
}


def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Аkkаунт", callback_data="account")
    builder.button(text="Трuггеры", callback_data="triggers")
    builder.button(text="Настройки", callback_data="settings")
    builder.adjust(1)
    return builder.as_markup()


def account_menu(has_account: bool, connected: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not has_account:
        builder.button(text="Подключить аkkаунт", callback_data="account:add")
    else:
        builder.button(text="Статус аkkаунта", callback_data="account:status")
        builder.button(
            text="Переподключить", callback_data="account:reconnect"
        )
        builder.button(text="Отключить", callback_data="account:disconnect")
    builder.button(text="Назад", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def disconnect_confirmation() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Да, отключить", callback_data="account:disconnect_confirm"
    )
    builder.button(text="Отмена", callback_data="account")
    builder.adjust(1)
    return builder.as_markup()


def code_keyboard() -> InlineKeyboardMarkup:
    digits = list(range(10))
    random.SystemRandom().shuffle(digits)
    rows = []
    for index in range(0, 9, 3):
        rows.append(
            [
                InlineKeyboardButton(
                    text=str(digit), callback_data=f"code:{digit}"
                )
                for digit in digits[index : index + 3]
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="⌫", callback_data="code:back"),
            InlineKeyboardButton(
                text=str(digits[9]), callback_data=f"code:{digits[9]}"
            ),
            InlineKeyboardButton(text="Готово", callback_data="code:submit"),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="Отмена", callback_data="code:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def match_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in MATCH_LABELS.items():
        builder.button(text=label, callback_data=f"match:{key}")
    builder.button(text="Отмена", callback_data="flow:cancel")
    builder.adjust(1)
    return builder.as_markup()


def triggers_menu(triggers: list[Trigger]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Добавить триггер", callback_data="trigger:add")
    for trigger in triggers:
        state = "🟢" if trigger.enabled else "⚪"
        title = trigger.text if len(trigger.text) <= 28 else trigger.text[:27] + "…"
        builder.button(
            text=f"{state} #{trigger.id} {title}",
            callback_data=f"trigger:view:{trigger.id}",
        )
    builder.button(text="Назад", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def trigger_menu(
    trigger: Trigger, chats: list[TriggerChat]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Добавить чат по ID",
        callback_data=f"trigger:chat_add:{trigger.id}",
    )
    for chat in chats:
        title = chat.title if len(chat.title) <= 22 else chat.title[:21] + "…"
        builder.button(
            text=f"✕ {title} ({chat.chat_id})",
            callback_data=f"trigger:chat_remove:{trigger.id}:{chat.chat_id}",
        )
    builder.button(
        text="Выключить" if trigger.enabled else "Включить",
        callback_data=f"trigger:toggle:{trigger.id}",
    )
    builder.button(
        text="Удалить", callback_data=f"trigger:delete:{trigger.id}"
    )
    builder.button(text="Назад", callback_data="triggers")
    builder.adjust(1)
    return builder.as_markup()


def delete_confirmation(trigger_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Да, удалить", callback_data=f"trigger:confirm:{trigger_id}"
    )
    builder.button(
        text="Отмена", callback_data=f"trigger:view:{trigger_id}"
    )
    builder.adjust(1)
    return builder.as_markup()


def settings_menu(
    process_private: bool, process_groups: bool, cooldown: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"Личные: {'вкл' if process_private else 'выкл'}",
        callback_data="setting:process_private",
    )
    builder.button(
        text=f"Группы: {'вкл' if process_groups else 'выкл'}",
        callback_data="setting:process_groups",
    )
    builder.button(
        text=f"Cooldown: {cooldown} сек.",
        callback_data="setting:cooldown",
    )
    builder.button(text="Назад", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="flow:cancel")]
        ]
    )
