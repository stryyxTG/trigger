import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from database import MAX_TRIGGER_CHATS, Database, Trigger
from userbot import trigger_matches


class TriggerMatchingTests(unittest.TestCase):
    def trigger(self, text: str, match_type: str) -> Trigger:
        return Trigger(1, text, match_type, "response", True)

    def test_contains_is_case_insensitive(self) -> None:
        self.assertTrue(
            trigger_matches(self.trigger("ПрИвЕт", "contains"), "Ну привет!")
        )

    def test_exact(self) -> None:
        trigger = self.trigger("hello", "exact")
        self.assertTrue(trigger_matches(trigger, "HELLO"))
        self.assertFalse(trigger_matches(trigger, "hello!"))

    def test_starts(self) -> None:
        trigger = self.trigger("заказ", "starts")
        self.assertTrue(trigger_matches(trigger, "Заказ готов"))
        self.assertFalse(trigger_matches(trigger, "Ваш заказ готов"))


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.db")
        await self.db.connect()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.temp_dir.cleanup()

    async def test_trigger_lifecycle_and_message_claim(self) -> None:
        trigger_id = await self.db.add_trigger("hello", "contains", "Hi")
        trigger = await self.db.get_trigger(trigger_id)
        self.assertIsNotNone(trigger)
        self.assertTrue(trigger.enabled)

        await self.db.toggle_trigger(trigger_id)
        trigger = await self.db.get_trigger(trigger_id)
        self.assertFalse(trigger.enabled)

        self.assertTrue(await self.db.claim_message(100, 200))
        self.assertFalse(await self.db.claim_message(100, 200))

    async def test_trigger_chat_scope(self) -> None:
        first_id = await self.db.add_trigger("first", "contains", "1")
        second_id = await self.db.add_trigger("second", "contains", "2")
        self.assertEqual(await self.db.list_triggers_for_chat(-1001), [])

        await self.db.add_trigger_chat(first_id, -1001, "Test group")
        scoped = await self.db.list_triggers_for_chat(-1001)
        self.assertEqual([trigger.id for trigger in scoped], [first_id])

        chats = await self.db.list_trigger_chats(first_id)
        self.assertEqual(chats[0].chat_id, -1001)
        self.assertEqual(chats[0].title, "Test group")

        await self.db.add_trigger_chat(second_id, -1001, "Test group")
        scoped = await self.db.list_triggers_for_chat(-1001)
        self.assertEqual(
            [trigger.id for trigger in scoped], [first_id, second_id]
        )

        await self.db.remove_trigger_chat(first_id, -1001)
        scoped = await self.db.list_triggers_for_chat(-1001)
        self.assertEqual([trigger.id for trigger in scoped], [second_id])

    async def test_trigger_chat_limit(self) -> None:
        trigger_id = await self.db.add_trigger("hello", "contains", "Hi")
        for index in range(MAX_TRIGGER_CHATS):
            await self.db.add_trigger_chat(
                trigger_id, -1000000 - index, f"Chat {index}"
            )
        with self.assertRaises(ValueError):
            await self.db.add_trigger_chat(
                trigger_id, -2000000, "One chat too many"
            )
        await self.db.add_trigger_chat(
            trigger_id, -1000000, "Renamed chat"
        )

    async def test_settings_and_cooldown(self) -> None:
        await self.db.set_cooldown(60)
        settings = await self.db.get_settings()
        self.assertEqual(settings["cooldown_seconds"], 60)
        self.assertTrue(await self.db.cooldown_ready(100, 60))
        await self.db.touch_cooldown(100)
        self.assertFalse(await self.db.cooldown_ready(100, 60))


if __name__ == "__main__":
    unittest.main()
