"""Хранилище загруженных чатов (экспортов Telegram Desktop).

Экспорт читается один раз, а в каталоге данных пользователя остаётся сжатая выжимка: тексты и
моменты сообщений каждого участника. Исходный `result.json` после загрузки можно удалить. Файлы
содержат реальные переписки, поэтому лежат только в каталоге данных и никогда не попадают в git.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from chatstyle.collectors.tg_export import read_tg_export_chat
from chatstyle.errors import ChatstyleError
from chatstyle.paths import data_dir
from chatstyle.timeline import Messages

_VERSION = 1


@dataclass(frozen=True)
class StoredSender:
    """Участник загруженного чата."""

    key: str  # from_id (или имя, если id нет)
    name: str  # имя для показа
    messages: int


@dataclass(frozen=True)
class StoredChat:
    """Загруженный чат."""

    id: str
    name: str
    added: str  # YYYY-MM-DD
    updated: str  # YYYY-MM-DD
    senders: tuple[StoredSender, ...]

    @property
    def messages(self) -> int:
        return sum(sender.messages for sender in self.senders)


def chats_dir(directory: Path | None = None) -> Path:
    """Каталог загруженных чатов: `directory` (для тестов) или `<данные пользователя>/chats`."""
    return directory if directory is not None else data_dir() / "chats"


def _file_name(chat_id: str) -> str:
    return re.sub(r"[^\w.-]", "_", chat_id) + ".json"


def _read(path: Path) -> dict[str, Any] | None:
    """Словарь чата или None, если файл не читается, повреждён или другой версии."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != _VERSION:
        return None
    if not isinstance(data.get("id"), str) or not isinstance(data.get("senders"), dict):
        return None
    return data


def _stored(data: dict[str, Any]) -> StoredChat:
    senders = tuple(
        StoredSender(key=key, name=str(item.get("name", key)), messages=len(item["messages"]))
        for key, item in data["senders"].items()
    )
    return StoredChat(
        id=data["id"],
        name=str(data.get("name", data["id"])),
        added=str(data.get("added", "")),
        updated=str(data.get("updated", "")),
        senders=senders,
    )


def _merge(old: dict[str, Any] | None, new: Messages) -> tuple[list[str], list[int | None]]:
    """Старые и новые сообщения участника без дублей по паре (текст, время), по времени."""
    times_new = new.times if new.times is not None else [None] * len(new)
    pairs: list[tuple[str, int | None]] = []
    if old is not None:
        pairs.extend(zip(old["messages"], old["times"], strict=True))
    pairs.extend(zip(new, times_new, strict=True))
    unique = list(dict.fromkeys(pairs))
    # стабильная сортировка: сообщения без времени остаются после всех, в своём порядке
    unique.sort(key=lambda pair: (pair[1] is None, pair[1] or 0))
    return [text for text, _ in unique], [moment for _, moment in unique]


def import_chat(path: Path, directory: Path | None = None) -> StoredChat:
    """Загрузить экспорт чата в список; повторная загрузка дополняет чат без дублей."""
    export = read_tg_export_chat(path)
    if not export.senders:
        raise ChatstyleError("В экспорте нет текстовых сообщений.")
    chat_id = export.chat_id
    if not chat_id:
        seed = (export.name or "chat").encode("utf-8")
        chat_id = "x" + hashlib.sha256(seed).hexdigest()[:10]

    target = chats_dir(directory) / _file_name(chat_id)
    previous = _read(target) if target.exists() else None
    today = date.today().isoformat()

    senders: dict[str, Any] = {}
    for key, (name, messages) in export.senders.items():
        old = previous["senders"].get(key) if previous is not None else None
        texts, times = _merge(old, messages)
        senders[key] = {"name": name, "messages": texts, "times": times}
    if previous is not None:  # участники, которых в новом экспорте нет, не пропадают
        for key, item in previous["senders"].items():
            senders.setdefault(key, item)

    data = {
        "version": _VERSION,
        "id": chat_id,
        "name": export.name or chat_id,
        "added": str(previous.get("added", today)) if previous is not None else today,
        "updated": today,
        "senders": senders,
    }
    temp = target.with_suffix(".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, target)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise ChatstyleError(f"Не удалось сохранить чат: {exc}") from exc
    return _stored(data)


def list_chats(directory: Path | None = None) -> list[StoredChat]:
    """Загруженные чаты: сначала недавно обновлённые, при равенстве по названию."""
    folder = chats_dir(directory)
    if not folder.is_dir():
        return []
    chats = []
    for path in folder.glob("*.json"):
        data = _read(path)
        if data is not None:
            chats.append(_stored(data))
    chats.sort(key=lambda chat: chat.name.casefold())
    chats.sort(key=lambda chat: chat.updated, reverse=True)
    return chats


def get_chat(ref: str, directory: Path | None = None) -> StoredChat:
    """Чат по точному id, а если такого нет, по названию (без учёта регистра)."""
    chats = list_chats(directory)
    for chat in chats:
        if chat.id == ref:
            return chat
    matches = [chat for chat in chats if chat.name.casefold() == ref.casefold()]
    if len(matches) > 1:
        raise ChatstyleError(f"Название «{ref}» неоднозначно, укажите id.")
    if not matches:
        raise ChatstyleError(f"Чат «{ref}» не найден среди загруженных.")
    return matches[0]


def remove_chat(ref: str, directory: Path | None = None) -> None:
    """Удалить загруженный чат (id или название)."""
    chat = get_chat(ref, directory)
    (chats_dir(directory) / _file_name(chat.id)).unlink(missing_ok=True)


def read_chat_sender(value: str, directory: Path | None = None) -> Messages:
    """Сообщения участника загруженного чата по значению источника `chat:`: «чат#участник».

    Чат задаётся id или названием, участник — ключом или точным именем.
    """
    ref, separator, who = value.rpartition("#")
    ref, who = ref.strip(), who.strip()
    if not separator or not ref or not who:
        raise ChatstyleError("Укажите чат и участника: chat:чат#Имя.")
    chat = get_chat(ref, directory)
    data = _read(chats_dir(directory) / _file_name(chat.id))
    if data is None:
        raise ChatstyleError(f"Чат «{ref}» не найден среди загруженных.")
    senders: dict[str, Any] = data["senders"]
    key = who if who in senders else None
    if key is None:
        named = [k for k, item in senders.items() if item.get("name") == who]
        if len(named) > 1:
            raise ChatstyleError(f"Имя «{who}» неоднозначно, укажите идентификатор участника.")
        if not named:
            raise ChatstyleError(f"Участник «{who}» не найден в чате «{chat.name}».")
        key = named[0]
    item = senders[key]
    return Messages(item["messages"], item["times"])
