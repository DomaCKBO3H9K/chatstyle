"""Локальный кэш сообщений, собранных из Telegram.

Кэш хранит реальные переписки, поэтому лежит только в каталоге данных пользователя
и никогда не попадает в репозиторий.
"""

import hashlib
import json
import os
from pathlib import Path

from chatstyle.paths import cache_dir
from chatstyle.timeline import Messages

_VERSION = 2  # версия 1 (без времени) не читается: сообщения загружаются заново


def _cache_path(chat: str, sender: str, limit: int, directory: Path | None) -> Path:
    key = f"{chat}\0{sender}\0{limit}".encode()
    name = hashlib.sha256(key).hexdigest()[:24] + ".json"
    return (directory if directory is not None else cache_dir()) / name


def load_cached(
    chat: str, sender: str, limit: int, directory: Path | None = None
) -> Messages | None:
    """Вернуть сохранённые сообщения или None, если кэша нет или он повреждён."""
    path = _cache_path(chat, sender, limit, directory)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != _VERSION:
        return None
    messages = data.get("messages")
    if not isinstance(messages, list) or not all(isinstance(m, str) for m in messages):
        return None
    times = data.get("times")
    if times is not None and (
        not isinstance(times, list)
        or len(times) != len(messages)
        or not all(m is None or (isinstance(m, int) and not isinstance(m, bool)) for m in times)
    ):
        return None
    return Messages(messages, times)


def store_cached(
    chat: str,
    sender: str,
    limit: int,
    messages: list[str],
    directory: Path | None = None,
) -> None:
    """Сохранить сообщения; запись атомарная, ошибки записи кэша не критичны."""
    path = _cache_path(chat, sender, limit, directory)
    payload = {
        "version": _VERSION,
        "chat": chat,
        "sender": sender,
        "limit": limit,
        "messages": list(messages),
        "times": getattr(messages, "times", None),
    }
    temp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        temp.unlink(missing_ok=True)
