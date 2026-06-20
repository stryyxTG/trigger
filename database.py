from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite


MATCH_TYPES = {"contains", "exact", "starts"}
MAX_TRIGGER_CHATS = 20


@dataclass(slots=True)
class Trigger:
    id: int
    text: str
    match_type: str
    response: str
    enabled: bool


@dataclass(slots=True)
class TriggerChat:
    trigger_id: int
    chat_id: int
    title: str


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.connection = await aiosqlite.connect(self.path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA journal_mode=WAL")
        await self.connection.execute("PRAGMA foreign_keys=ON")
        await self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                phone TEXT,
                telegram_user_id INTEGER,
                username TEXT,
                connected INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                process_private INTEGER NOT NULL DEFAULT 1,
                process_groups INTEGER NOT NULL DEFAULT 1,
                cooldown_seconds INTEGER NOT NULL DEFAULT 30
            );

            CREATE TABLE IF NOT EXISTS triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                match_type TEXT NOT NULL CHECK (
                    match_type IN ('contains', 'exact', 'starts')
                ),
                response TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trigger_chats (
                trigger_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                added_at INTEGER NOT NULL,
                PRIMARY KEY (trigger_id, chat_id),
                FOREIGN KEY (trigger_id) REFERENCES triggers(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS processed_messages (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                processed_at INTEGER NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            );

            CREATE TABLE IF NOT EXISTS cooldowns (
                chat_id INTEGER PRIMARY KEY,
                responded_at INTEGER NOT NULL
            );

            INSERT OR IGNORE INTO settings (id) VALUES (1);
            """
        )
        await self.connection.commit()

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    def _db(self) -> aiosqlite.Connection:
        if self.connection is None:
            raise RuntimeError("База данных не подключена")
        return self.connection

    async def get_account(self) -> aiosqlite.Row | None:
        cursor = await self._db().execute("SELECT * FROM account WHERE id = 1")
        return await cursor.fetchone()

    async def save_account(
        self, phone: str, user_id: int, username: str | None, connected: bool
    ) -> None:
        await self._db().execute(
            """
            INSERT INTO account
                (id, phone, telegram_user_id, username, connected, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                phone = excluded.phone,
                telegram_user_id = excluded.telegram_user_id,
                username = excluded.username,
                connected = excluded.connected,
                updated_at = excluded.updated_at
            """,
            (phone, user_id, username, int(connected), int(time.time())),
        )
        await self._db().commit()

    async def set_account_connected(self, connected: bool) -> None:
        await self._db().execute(
            "UPDATE account SET connected = ?, updated_at = ? WHERE id = 1",
            (int(connected), int(time.time())),
        )
        await self._db().commit()

    async def clear_account(self) -> None:
        await self._db().execute("DELETE FROM account WHERE id = 1")
        await self._db().commit()

    async def get_settings(self) -> aiosqlite.Row:
        cursor = await self._db().execute("SELECT * FROM settings WHERE id = 1")
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Настройки не инициализированы")
        return row

    async def toggle_setting(self, name: str) -> None:
        if name not in {"process_private", "process_groups"}:
            raise ValueError("Неизвестная настройка")
        await self._db().execute(
            f"UPDATE settings SET {name} = NOT {name} WHERE id = 1"
        )
        await self._db().commit()

    async def set_cooldown(self, seconds: int) -> None:
        await self._db().execute(
            "UPDATE settings SET cooldown_seconds = ? WHERE id = 1", (seconds,)
        )
        await self._db().commit()

    async def add_trigger(
        self, text: str, match_type: str, response: str
    ) -> int:
        if match_type not in MATCH_TYPES:
            raise ValueError("Неизвестный тип совпадения")
        cursor = await self._db().execute(
            """
            INSERT INTO triggers (text, match_type, response, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (text, match_type, response, int(time.time())),
        )
        await self._db().commit()
        return int(cursor.lastrowid)

    async def list_triggers(self, enabled_only: bool = False) -> list[Trigger]:
        query = "SELECT * FROM triggers"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY id"
        cursor = await self._db().execute(query)
        rows = await cursor.fetchall()
        return [
            Trigger(
                id=row["id"],
                text=row["text"],
                match_type=row["match_type"],
                response=row["response"],
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    async def list_triggers_for_chat(self, chat_id: int) -> list[Trigger]:
        cursor = await self._db().execute(
            """
            SELECT t.*
            FROM triggers AS t
            INNER JOIN trigger_chats AS tc ON tc.trigger_id = t.id
            WHERE t.enabled = 1 AND tc.chat_id = ?
            ORDER BY t.id
            """,
            (chat_id,),
        )
        rows = await cursor.fetchall()
        return [
            Trigger(
                id=row["id"],
                text=row["text"],
                match_type=row["match_type"],
                response=row["response"],
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    async def get_trigger(self, trigger_id: int) -> Trigger | None:
        cursor = await self._db().execute(
            "SELECT * FROM triggers WHERE id = ?", (trigger_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Trigger(
            id=row["id"],
            text=row["text"],
            match_type=row["match_type"],
            response=row["response"],
            enabled=bool(row["enabled"]),
        )

    async def toggle_trigger(self, trigger_id: int) -> None:
        await self._db().execute(
            "UPDATE triggers SET enabled = NOT enabled WHERE id = ?",
            (trigger_id,),
        )
        await self._db().commit()

    async def list_trigger_chats(self, trigger_id: int) -> list[TriggerChat]:
        cursor = await self._db().execute(
            """
            SELECT trigger_id, chat_id, title
            FROM trigger_chats
            WHERE trigger_id = ?
            ORDER BY title COLLATE NOCASE, chat_id
            """,
            (trigger_id,),
        )
        rows = await cursor.fetchall()
        return [
            TriggerChat(
                trigger_id=row["trigger_id"],
                chat_id=row["chat_id"],
                title=row["title"],
            )
            for row in rows
        ]

    async def add_trigger_chat(
        self, trigger_id: int, chat_id: int, title: str
    ) -> None:
        cursor = await self._db().execute(
            """
            SELECT COUNT(*) AS count
            FROM trigger_chats
            WHERE trigger_id = ? AND chat_id != ?
            """,
            (trigger_id, chat_id),
        )
        row = await cursor.fetchone()
        if row is not None and row["count"] >= MAX_TRIGGER_CHATS:
            raise ValueError(
                f"К одному триггеру можно добавить не более "
                f"{MAX_TRIGGER_CHATS} чатов"
            )
        await self._db().execute(
            """
            INSERT INTO trigger_chats (trigger_id, chat_id, title, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(trigger_id, chat_id) DO UPDATE SET
                title = excluded.title,
                added_at = excluded.added_at
            """,
            (trigger_id, chat_id, title, int(time.time())),
        )
        await self._db().commit()

    async def remove_trigger_chat(
        self, trigger_id: int, chat_id: int
    ) -> None:
        await self._db().execute(
            "DELETE FROM trigger_chats WHERE trigger_id = ? AND chat_id = ?",
            (trigger_id, chat_id),
        )
        await self._db().commit()

    async def delete_trigger(self, trigger_id: int) -> None:
        await self._db().execute(
            "DELETE FROM triggers WHERE id = ?", (trigger_id,)
        )
        await self._db().commit()

    async def claim_message(self, chat_id: int, message_id: int) -> bool:
        cursor = await self._db().execute(
            """
            INSERT OR IGNORE INTO processed_messages
                (chat_id, message_id, processed_at)
            VALUES (?, ?, ?)
            """,
            (chat_id, message_id, int(time.time())),
        )
        await self._db().commit()
        return cursor.rowcount == 1

    async def cooldown_ready(self, chat_id: int, seconds: int) -> bool:
        cursor = await self._db().execute(
            "SELECT responded_at FROM cooldowns WHERE chat_id = ?", (chat_id,)
        )
        row = await cursor.fetchone()
        return row is None or int(time.time()) - row["responded_at"] >= seconds

    async def touch_cooldown(self, chat_id: int) -> None:
        await self._db().execute(
            """
            INSERT INTO cooldowns (chat_id, responded_at) VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET responded_at = excluded.responded_at
            """,
            (chat_id, int(time.time())),
        )
        await self._db().commit()

    async def cleanup_processed(self, max_age_days: int = 30) -> None:
        cutoff = int(time.time()) - max_age_days * 86400
        await self._db().execute(
            "DELETE FROM processed_messages WHERE processed_at < ?", (cutoff,)
        )
        await self._db().commit()
