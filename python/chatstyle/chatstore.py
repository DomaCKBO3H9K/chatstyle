"""Хранилище загруженных чатов (экспортов Telegram Desktop).

Экспорт читается один раз, а в каталоге данных пользователя остаётся сжатая выжимка: тексты и
моменты сообщений каждого участника. Исходный `result.json` после загрузки можно удалить.

Выжимка содержит реальные переписки, поэтому в рабочем режиме хранится ЗАШИФРОВАННОЙ
(AES-256-GCM, `chatcrypt`): ключ случайный, лежит в общем хранилище секретов (`vault.json`,
мастер-пароль или DPAPI). В режиме хранилища «только на время окна» чаты живут только в памяти
процесса и исчезают вместе с ним. Старые открытые файлы (`*.json`) при первом открытии
шифруются, а открытые копии затираются и удаляются. Файлы лежат только в каталоге данных и
никогда не попадают в git.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from chatstyle import chatcrypt
from chatstyle.collectors.tg_export import read_tg_export_chat
from chatstyle.errors import ChatstyleError, CodedError
from chatstyle.paths import data_dir
from chatstyle.securestore import MODE_DPAPI, MODE_MEMORY, default_vault
from chatstyle.timeline import Messages

_VERSION = 1
VAULT_KEY = "chats_key"  # ключ шифрования чатов в хранилище секретов
SUFFIX = ".chat"  # зашифрованный файл чата
LEGACY_SUFFIX = ".json"  # открытый файл (версия 1): читается, при открытии хранилища шифруется


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


def legacy_plain_chats() -> int:
    """Сколько открытых файлов чатов прежнего формата лежит в рабочей папке (не зашифрованы)."""
    folder = chats_dir(None)
    return len(list(folder.glob(f"*{LEGACY_SUFFIX}"))) if folder.is_dir() else 0


def _stem(chat_id: str) -> str:
    """Имя файла чата без суффикса; оно же служит «id» при шифровании (привязка к файлу)."""
    return re.sub(r"[^\w.-]", "_", chat_id)


def _valid(data: object) -> dict[str, Any] | None:
    """Словарь чата, если он нужной версии и формы, иначе None."""
    if not isinstance(data, dict) or data.get("version") != _VERSION:
        return None
    if not isinstance(data.get("id"), str) or not isinstance(data.get("senders"), dict):
        return None
    return data


class _Backend(Protocol):
    def stems(self) -> list[str]: ...

    def load(self, stem: str) -> dict[str, Any] | None: ...

    def save(self, stem: str, data: dict[str, Any]) -> None: ...

    def delete(self, stem: str) -> None: ...


class _Disk:
    """Файлы в каталоге. Без ключа — открытый JSON (тесты и инструменты), с ключом — шифрование."""

    def __init__(self, folder: Path, key: bytes | None) -> None:
        self._folder = folder
        self._key = key

    def _plain(self, stem: str) -> Path:
        return self._folder / f"{stem}{LEGACY_SUFFIX}"

    def _encrypted(self, stem: str) -> Path:
        return self._folder / f"{stem}{SUFFIX}"

    def stems(self) -> list[str]:
        if not self._folder.is_dir():
            return []
        found = {path.stem for path in self._folder.glob(f"*{LEGACY_SUFFIX}")}
        if self._key is not None:
            found |= {path.stem for path in self._folder.glob(f"*{SUFFIX}")}
        return sorted(found)

    def load(self, stem: str) -> dict[str, Any] | None:
        encrypted = self._encrypted(stem)
        if self._key is not None and encrypted.exists():
            try:
                blob = encrypted.read_bytes()
            except OSError:
                return None
            text = chatcrypt.decrypt(self._key, blob, stem)  # ошибка расшифровки не скрывается
            return _parse(text)
        plain = self._plain(stem)
        try:
            return _parse(plain.read_bytes())
        except OSError:
            return None

    def save(self, stem: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if self._key is None:
            target = self._plain(stem)
        else:
            target = self._encrypted(stem)
            payload = chatcrypt.encrypt(self._key, payload, stem)
        temp = target.with_suffix(".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(payload)
            os.replace(temp, target)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise ChatstyleError(f"Не удалось сохранить чат: {exc}") from exc
        if self._key is not None:
            chatcrypt.wipe_file(self._plain(stem))  # открытая копия старого формата

    def delete(self, stem: str) -> None:
        chatcrypt.wipe_file(self._encrypted(stem))
        chatcrypt.wipe_file(self._plain(stem))

    def migrate(self) -> None:
        """Зашифровать открытые файлы прежнего формата (открытые копии затираются)."""
        if self._key is None:
            return
        for stem in self.stems():
            if self._encrypted(stem).exists():
                chatcrypt.wipe_file(self._plain(stem))
                continue
            data = self.load(stem)
            if data is not None:
                self.save(stem, data)


def _parse(raw: bytes) -> dict[str, Any] | None:
    try:
        return _valid(json.loads(raw.decode("utf-8")))
    except ValueError:
        return None


_MEMORY: dict[str, dict[str, Any]] = {}  # режим «только на время окна»: чаты только в памяти


class _Memory:
    """Чаты в памяти процесса (режим хранилища «только на время окна»)."""

    def stems(self) -> list[str]:
        return sorted(_MEMORY)

    def load(self, stem: str) -> dict[str, Any] | None:
        data = _MEMORY.get(stem)
        return copy.deepcopy(data) if data is not None else None

    def save(self, stem: str, data: dict[str, Any]) -> None:
        _MEMORY[stem] = copy.deepcopy(data)

    def delete(self, stem: str) -> None:
        _MEMORY.pop(stem, None)


def _backend(directory: Path | None, key: bytes | None) -> _Backend:
    """Куда складывать чаты.

    С `directory` — файлы в этом каталоге (тесты и инструменты; без `key` открытым JSON). Без
    него — рабочий режим: ключ берётся из хранилища секретов, которое должно быть создано и
    открыто, иначе CodedError `chats_setup` / `chats_locked`.
    """
    if directory is not None:
        return _Disk(chats_dir(directory), key)
    vault = default_vault()
    mode = vault.mode()
    if mode is None:
        raise CodedError(
            "chats_setup",
            "Чтобы хранить чаты, задайте защиту (мастер-пароль, DPAPI или «только на время окна»).",
        )
    if mode == MODE_MEMORY:
        return _Memory()
    if not vault.unlocked():
        if mode != MODE_DPAPI:
            raise CodedError("chats_locked", "Хранилище закрыто: введите мастер-пароль.")
        vault.unlock()  # DPAPI открывается без пароля
    stored = vault.get(VAULT_KEY)
    if stored is None:
        secret = chatcrypt.new_key()
        vault.set(VAULT_KEY, chatcrypt.encode_key(secret))
    else:
        secret = chatcrypt.decode_key(stored)
    disk = _Disk(chats_dir(None), secret)
    disk.migrate()
    return disk


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


def import_chat(
    path: Path, directory: Path | None = None, *, key: bytes | None = None
) -> StoredChat:
    """Загрузить экспорт чата в список; повторная загрузка дополняет чат без дублей."""
    export = read_tg_export_chat(path)
    if not export.senders:
        raise ChatstyleError("В экспорте нет текстовых сообщений.")
    chat_id = export.chat_id
    if not chat_id:
        seed = (export.name or "chat").encode("utf-8")
        chat_id = "x" + hashlib.sha256(seed).hexdigest()[:10]

    backend = _backend(directory, key)
    stem = _stem(chat_id)
    previous = backend.load(stem)
    today = date.today().isoformat()

    senders: dict[str, Any] = {}
    for sender_key, (name, messages) in export.senders.items():
        old = previous["senders"].get(sender_key) if previous is not None else None
        texts, times = _merge(old, messages)
        senders[sender_key] = {"name": name, "messages": texts, "times": times}
    if previous is not None:  # участники, которых в новом экспорте нет, не пропадают
        for sender_key, item in previous["senders"].items():
            senders.setdefault(sender_key, item)

    data = {
        "version": _VERSION,
        "id": chat_id,
        "name": export.name or chat_id,
        "added": str(previous.get("added", today)) if previous is not None else today,
        "updated": today,
        "senders": senders,
    }
    backend.save(stem, data)
    return _stored(data)


def list_chats(directory: Path | None = None, *, key: bytes | None = None) -> list[StoredChat]:
    """Загруженные чаты: сначала недавно обновлённые, при равенстве по названию."""
    backend = _backend(directory, key)
    chats = []
    for stem in backend.stems():
        data = backend.load(stem)
        if data is not None:
            chats.append(_stored(data))
    chats.sort(key=lambda chat: chat.name.casefold())
    chats.sort(key=lambda chat: chat.updated, reverse=True)
    return chats


def get_chat(ref: str, directory: Path | None = None, *, key: bytes | None = None) -> StoredChat:
    """Чат по точному id, а если такого нет, по названию (без учёта регистра)."""
    chats = list_chats(directory, key=key)
    for chat in chats:
        if chat.id == ref:
            return chat
    matches = [chat for chat in chats if chat.name.casefold() == ref.casefold()]
    if len(matches) > 1:
        raise ChatstyleError(f"Название «{ref}» неоднозначно, укажите id.")
    if not matches:
        raise ChatstyleError(f"Чат «{ref}» не найден среди загруженных.")
    return matches[0]


def remove_chat(ref: str, directory: Path | None = None, *, key: bytes | None = None) -> None:
    """Удалить загруженный чат (id или название); файлы затираются."""
    chat = get_chat(ref, directory, key=key)
    _backend(directory, key).delete(_stem(chat.id))


def read_chat_sender(
    value: str, directory: Path | None = None, *, key: bytes | None = None
) -> Messages:
    """Сообщения участника загруженного чата по значению источника `chat:`: «чат#участник».

    Чат задаётся id или названием, участник — ключом или точным именем.
    """
    ref, separator, who = value.rpartition("#")
    ref, who = ref.strip(), who.strip()
    if not separator or not ref or not who:
        raise ChatstyleError("Укажите чат и участника: chat:чат#Имя.")
    chat = get_chat(ref, directory, key=key)
    data = _backend(directory, key).load(_stem(chat.id))
    if data is None:
        raise ChatstyleError(f"Чат «{ref}» не найден среди загруженных.")
    senders: dict[str, Any] = data["senders"]
    found = who if who in senders else None
    if found is None:
        named = [k for k, item in senders.items() if item.get("name") == who]
        if len(named) > 1:
            raise ChatstyleError(f"Имя «{who}» неоднозначно, укажите идентификатор участника.")
        if not named:
            raise ChatstyleError(f"Участник «{who}» не найден в чате «{chat.name}».")
        found = named[0]
    item = senders[found]
    return Messages(item["messages"], item["times"])
