import unittest

from aiogram.types import InlineKeyboardMarkup

from bot import trigger_card_text
from database import MAX_TRIGGER_CHATS, Trigger, TriggerChat
from keyboards import (
    account_menu,
    code_keyboard,
    main_menu,
    settings_menu,
    trigger_menu,
)


def callback_values(markup: InlineKeyboardMarkup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


class BotInterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trigger = Trigger(1, "hello", "contains", "Hi", True)

    def test_main_callbacks(self) -> None:
        self.assertEqual(
            callback_values(main_menu()),
            ["account", "triggers", "settings"],
        )
        self.assertIn(
            "account:add", callback_values(account_menu(False, False))
        )
        self.assertIn(
            "account:reconnect", callback_values(account_menu(True, False))
        )

    def test_code_keyboard_contains_all_digits_and_actions(self) -> None:
        values = callback_values(code_keyboard())
        self.assertEqual(
            sorted(value for value in values if value[5:].isdigit()),
            [f"code:{digit}" for digit in range(10)],
        )
        self.assertIn("code:back", values)
        self.assertIn("code:submit", values)
        self.assertIn("code:cancel", values)

    def test_trigger_chat_callbacks_fit_telegram_limit(self) -> None:
        chats = [
            TriggerChat(1, -1000000000000 - index, f"Chat {index}")
            for index in range(MAX_TRIGGER_CHATS)
        ]
        values = callback_values(trigger_menu(self.trigger, chats))
        self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in values))

    def test_trigger_card_fits_message_limit(self) -> None:
        trigger = Trigger(
            1,
            "т" * 500,
            "contains",
            "о" * 4096,
            True,
        )
        chats = [
            TriggerChat(1, -1000000000000 - index, "Ч" * 128)
            for index in range(MAX_TRIGGER_CHATS)
        ]
        self.assertLessEqual(len(trigger_card_text(trigger, chats)), 4096)

    def test_settings_callbacks(self) -> None:
        self.assertEqual(
            callback_values(settings_menu(True, False, 30)),
            [
                "setting:process_private",
                "setting:process_groups",
                "setting:cooldown",
                "menu",
            ],
        )


if __name__ == "__main__":
    unittest.main()
