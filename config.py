from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    admin_id: int
    api_id: int
    api_hash: str
    data_dir: Path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "bot.db"

    @property
    def session_path(self) -> Path:
        return self.data_dir / "account"


def _read_local_config() -> dict[str, Any]:
    path = BASE_DIR / "config.local.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("config.local.json должен содержать JSON-объект")
    return data


def load_config() -> Config:
    local = _read_local_config()

    def value(name: str, default: Any = None) -> Any:
        return os.getenv(name, local.get(name, default))

    missing = [
        name
        for name in ("BOT_TOKEN", "ADMIN_ID", "API_ID", "API_HASH")
        if value(name) in (None, "")
    ]
    if missing:
        raise RuntimeError(
            "Не заданы обязательные параметры: " + ", ".join(missing)
        )

    bot_token = str(value("BOT_TOKEN")).strip()
    api_hash = str(value("API_HASH")).strip()
    try:
        admin_id = int(value("ADMIN_ID"))
        api_id = int(value("API_ID"))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "ADMIN_ID и API_ID должны быть целыми числами"
        ) from error

    token_parts = bot_token.split(":", 1)
    if (
        len(token_parts) != 2
        or not token_parts[0].isdigit()
        or not token_parts[1]
    ):
        raise ValueError("BOT_TOKEN имеет неверный формат")
    if admin_id <= 0:
        raise ValueError("ADMIN_ID должен быть положительным числом")
    if api_id <= 0:
        raise ValueError("API_ID должен быть положительным числом")
    if len(api_hash) != 32 or any(
        character not in "0123456789abcdefABCDEF"
        for character in api_hash
    ):
        raise ValueError(
            "API_HASH должен содержать 32 шестнадцатеричных символа"
        )

    data_dir = Path(str(value("DATA_DIR", "data")))
    if not data_dir.is_absolute():
        data_dir = BASE_DIR / data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=bot_token,
        admin_id=admin_id,
        api_id=api_id,
        api_hash=api_hash,
        data_dir=data_dir,
    )
