"""Ключи Telegram API: переменные окружения и файл .env."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from chatstyle.errors import ChatstyleError
from chatstyle.paths import env_file

API_ID_VAR = "TELEGRAM_API_ID"
API_HASH_VAR = "TELEGRAM_API_HASH"

_HELP = (
    f"Укажите {API_ID_VAR} и {API_HASH_VAR} (их выдаёт https://my.telegram.org, раздел "
    "API development tools) в переменных окружения или в файле .env."
)


@dataclass(frozen=True)
class TelegramCredentials:
    """Ключи приложения Telegram. api_hash скрыт из repr, чтобы не попасть в логи."""

    api_id: int
    api_hash: str = field(repr=False)


def parse_env_file(path: Path) -> dict[str, str]:
    """Прочитать .env: строки KEY=VALUE, комментарии #, необязательные кавычки и export."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return {}
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_telegram_credentials(
    environ: Mapping[str, str] | None = None,
    env_files: tuple[Path, ...] | None = None,
) -> TelegramCredentials:
    """Найти ключи: окружение, затем .env в текущей папке, затем .env в каталоге данных."""
    environment = os.environ if environ is None else environ
    files = (Path(".env"), env_file()) if env_files is None else env_files

    def lookup(name: str) -> str | None:
        value = environment.get(name)
        if value:
            return value.strip()
        for path in files:
            value = parse_env_file(path).get(name)
            if value:
                return value
        return None

    raw_id = lookup(API_ID_VAR)
    api_hash = lookup(API_HASH_VAR)
    if not raw_id or not api_hash:
        raise ChatstyleError(f"Не найдены ключи Telegram API. {_HELP}")
    try:
        api_id = int(raw_id)
    except ValueError as exc:
        raise ChatstyleError(f"{API_ID_VAR} должен быть числом. {_HELP}") from exc
    return TelegramCredentials(api_id=api_id, api_hash=api_hash)
