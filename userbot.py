from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import (
    AuthKeyError,
    AuthKeyUnregisteredError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl.types import User

from database import Database, Trigger


logger = logging.getLogger(__name__)
Notifier = Callable[[str], Awaitable[None]]


class UserbotError(Exception):
    pass


class InvalidCode(UserbotError):
    pass


class ExpiredCode(UserbotError):
    pass


class PasswordRequired(UserbotError):
    pass


class InvalidPassword(UserbotError):
    pass


def trigger_matches(trigger: Trigger, text: str) -> bool:
    needle = trigger.text.casefold()
    haystack = text.casefold()
    if trigger.match_type == "contains":
        return needle in haystack
    if trigger.match_type == "exact":
        return needle == haystack
    if trigger.match_type == "starts":
        return haystack.startswith(needle)
    return False


class UserbotManager:
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_path: Path,
        database: Database,
        notify: Notifier,
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.database = database
        self.notify = notify
        self.client: TelegramClient | None = None
        self.pending_phone: str | None = None
        self.pending_phone_code_hash: str | None = None
        self._response_lock = asyncio.Lock()
        self._watchdog_task: asyncio.Task[None] | None = None
        self._stopping = False

    def _new_client(self) -> TelegramClient:
        client = TelegramClient(
            str(self.session_path),
            self.api_id,
            self.api_hash,
            auto_reconnect=True,
            connection_retries=5,
            retry_delay=3,
        )
        client.add_event_handler(
            self._on_new_message, events.NewMessage(incoming=True)
        )
        return client

    async def start(self) -> None:
        self._stopping = False
        await self.database.cleanup_processed()
        account = await self.database.get_account()
        if account is not None:
            await self.connect_saved(notify_success=True)
        self._watchdog_task = asyncio.create_task(
            self._watchdog(), name="telethon-watchdog"
        )

    async def stop(self) -> None:
        self._stopping = True
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            await asyncio.gather(self._watchdog_task, return_exceptions=True)
            self._watchdog_task = None
        await self._discard_client()

    async def begin_login(self, phone: str) -> None:
        account = await self.database.get_account()
        if account is not None:
            raise UserbotError("Аккаунт уже добавлен")
        await self._discard_client()
        self.client = self._new_client()
        try:
            await self.client.connect()
            sent = await self.client.send_code_request(phone)
        except Exception:
            await self._discard_client()
            raise
        self.pending_phone = phone
        self.pending_phone_code_hash = sent.phone_code_hash

    async def submit_code(self, code: str) -> User:
        if (
            self.client is None
            or self.pending_phone is None
            or self.pending_phone_code_hash is None
        ):
            raise UserbotError("Авторизация не была начата")
        try:
            user = await self.client.sign_in(
                phone=self.pending_phone,
                code=code,
                phone_code_hash=self.pending_phone_code_hash,
            )
        except PhoneCodeInvalidError as error:
            raise InvalidCode("Неверный код") from error
        except PhoneCodeExpiredError as error:
            raise ExpiredCode("Срок действия кода истёк") from error
        except SessionPasswordNeededError as error:
            raise PasswordRequired("Нужен облачный пароль") from error
        await self._finish_login(user)
        return user

    async def submit_password(self, password: str) -> User:
        if self.client is None or self.pending_phone is None:
            raise UserbotError("Авторизация не была начата")
        try:
            user = await self.client.sign_in(password=password)
        except PasswordHashInvalidError as error:
            raise InvalidPassword("Неверный облачный пароль") from error
        await self._finish_login(user)
        return user

    async def _finish_login(self, user: User) -> None:
        phone = self.pending_phone or getattr(user, "phone", None) or ""
        await self.database.save_account(
            phone=phone,
            user_id=user.id,
            username=user.username,
            connected=True,
        )
        self.pending_phone = None
        self.pending_phone_code_hash = None

    async def connect_saved(self, notify_success: bool = True) -> bool:
        account = await self.database.get_account()
        if account is None:
            return False
        await self._discard_client()
        self.client = self._new_client()
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                await self.database.set_account_connected(False)
                await self.notify(
                    "Сохранённая сессия больше не авторизована. "
                    "Отключите её и подключите аккаунт заново."
                )
                await self._discard_client()
                return False
            user = await self.client.get_me()
            await self.database.save_account(
                phone=account["phone"] or getattr(user, "phone", ""),
                user_id=user.id,
                username=user.username,
                connected=True,
            )
            if notify_success:
                await self.notify("Пользовательский аккаунт переподключён.")
            return True
        except (AuthKeyError, AuthKeyUnregisteredError) as error:
            await self._handle_auth_loss(error)
        except sqlite3.Error as error:
            await self.database.set_account_connected(False)
            await self.notify(
                f"Локальная Telethon-сессия повреждена: {error}. "
                "Отключите аккаунт и подключите его заново."
            )
            await self._discard_client()
        except (OSError, asyncio.TimeoutError) as error:
            await self.database.set_account_connected(False)
            await self.notify(f"Сетевая ошибка подключения аккаунта: {error}")
            await self._discard_client()
        except Exception as error:
            logger.exception("Ошибка подключения сохранённой сессии")
            await self.database.set_account_connected(False)
            await self.notify(f"Ошибка подключения аккаунта: {error}")
            await self._discard_client()
        return False

    async def disconnect(self) -> None:
        if self.client is not None:
            await self.client.disconnect()
            self.client = None
        await self.database.set_account_connected(False)

    async def resolve_dialog(self, chat_id: int) -> str:
        if self.client is None or not self.client.is_connected():
            raise UserbotError(
                "Пользовательский аккаунт не подключён"
            )
        if not await self.client.is_user_authorized():
            raise UserbotError(
                "Сессия пользовательского аккаунта не авторизована"
            )
        async for dialog in self.client.iter_dialogs():
            if dialog.id == chat_id:
                return dialog.name or str(chat_id)
        raise UserbotError(
            "Диалог с таким ID не найден. Проверьте ID и убедитесь, "
            "что подключённый аккаунт состоит в этом чате."
        )

    async def stop_pending_login(self) -> None:
        self.pending_phone = None
        self.pending_phone_code_hash = None
        await self._discard_client()
        if await self.database.get_account() is None:
            self._delete_session_files()

    async def forget_account(self) -> None:
        await self._discard_client()
        await self.database.clear_account()
        self.pending_phone = None
        self.pending_phone_code_hash = None
        self._delete_session_files()

    def _delete_session_files(self) -> None:
        for suffix in (".session", ".session-journal"):
            path = Path(f"{self.session_path}{suffix}")
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Не удалось удалить файл сессии %s", path)

    async def _discard_client(self) -> None:
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                logger.exception("Ошибка при закрытии Telethon-клиента")
            self.client = None

    async def _handle_auth_loss(self, error: Exception) -> None:
        logger.error(
            "Потеря авторизации Telethon: %s", error, exc_info=True
        )
        await self.database.set_account_connected(False)
        await self.notify(
            "Telethon потерял авторизацию. Требуется повторное подключение."
        )
        await self._discard_client()

    async def _watchdog(self) -> None:
        while not self._stopping:
            await asyncio.sleep(15)
            account = await self.database.get_account()
            if account is None or not account["connected"]:
                continue
            if self.client is None or not self.client.is_connected():
                await self.notify(
                    "Соединение пользовательского аккаунта потеряно, "
                    "пытаюсь восстановить."
                )
                await self.connect_saved(notify_success=True)

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        try:
            await self._process_new_message(event)
        except (AuthKeyError, AuthKeyUnregisteredError) as error:
            await self._handle_auth_loss(error)
        except (OSError, asyncio.TimeoutError) as error:
            logger.warning("Сетевая ошибка при обработке сообщения: %s", error)
            await self.notify(f"Сетевая ошибка Telethon: {error}")
        except Exception as error:
            logger.exception("Ошибка обработки входящего сообщения")
            await self.notify(f"Ошибка обработки сообщения: {error}")

    async def _process_new_message(
        self, event: events.NewMessage.Event
    ) -> None:
        if event.out or not event.raw_text:
            return
        settings = await self.database.get_settings()
        if event.is_private and not settings["process_private"]:
            return
        if event.is_group and not settings["process_groups"]:
            return
        if not event.is_private and not event.is_group:
            return

        sender = await event.get_sender()
        if isinstance(sender, User) and sender.bot:
            return

        chat_id = event.chat_id
        if chat_id is None:
            return
        triggers = await self.database.list_triggers_for_chat(chat_id)
        for trigger in triggers:
            try:
                if not trigger_matches(trigger, event.raw_text):
                    continue
                await self._respond_once(event, trigger, settings["cooldown_seconds"])
                return
            except FloodWaitError as error:
                await self.notify(
                    f"FloodWait на {error.seconds} сек. "
                    f"для триггера #{trigger.id}; ответ пропущен."
                )
                return
            except Exception as error:
                logger.exception("Ошибка триггера %s", trigger.id)
                await self.notify(f"Ошибка триггера #{trigger.id}: {error}")

    async def _respond_once(
        self,
        event: events.NewMessage.Event,
        trigger: Trigger,
        cooldown_seconds: int,
    ) -> None:
        chat_id = event.chat_id
        if chat_id is None:
            return
        async with self._response_lock:
            if not await self.database.cooldown_ready(
                chat_id, cooldown_seconds
            ):
                return
            if not await self.database.claim_message(chat_id, event.id):
                return
            await event.reply(trigger.response)
            await self.database.touch_cooldown(chat_id)

        sender = await event.get_sender()
        sender_name = getattr(sender, "username", None) or getattr(
            sender, "first_name", None
        )
        await self.notify(
            f"Сработал триггер #{trigger.id} «{trigger.text}»\n"
            f"Диалог: {chat_id}\n"
            f"Отправитель: {sender_name or 'неизвестен'}"
        )
