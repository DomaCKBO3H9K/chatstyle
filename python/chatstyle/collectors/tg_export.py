"""Парсер JSON‑экспорта одного чата Telegram Desktop.

Функция :func:`read_tg_export` возвращает список текстов сообщений указанного
отправителя в порядке их появления в файле. При ошибках поднимается
:class:`chatstyle.errors.ChatstyleError` с русским сообщением.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from chatstyle.errors import ChatstyleError


def _matches(msg: dict[str, Any], sender: str) -> bool:
    """Проверить, принадлежит ли сообщение отправителю.

    Сравниваются поля ``from`` и ``from_id``. Если ``sender`` состоит только
    из цифр, допускаются варианты ``user{sender}`` и ``channel{sender}``.
    """
    from_name = msg.get("from")
    from_id = msg.get("from_id")
    if sender == from_name or sender == from_id:
        return True
    if sender.isdigit():
        return from_id in (f"user{sender}", f"channel{sender}")
    return False


def _flatten_text(text: Any) -> str:
    """Преобразовать поле ``text`` сообщения в одну строку.

    - Если ``text`` — строка, возвращается она же.
    - Если ``text`` — список, каждый элемент обрабатывается:
        * строка — берётся как есть;
        * словарь — берётся значение по ключу ``text`` (если это строка);
        * остальные типы игнорируются.
    - Для всех остальных типов возвращается пустая строка.
    """
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts: list[str] = []
        for item in text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                part = item.get("text")
                if isinstance(part, str):
                    parts.append(part)
        return "".join(parts)
    return ""


def _load_messages(path: Path) -> list[object]:
    """Прочитать экспорт одного чата и вернуть список его сообщений (сырые записи)."""
    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ChatstyleError(f"Не удалось прочитать файл {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ChatstyleError(f"Файл {path} не в кодировке UTF-8.") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ChatstyleError(f"Файл {path} не является корректным JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ChatstyleError(f"Файл {path} не похож на экспорт Telegram.")
    if "chats" in data:
        raise ChatstyleError(
            "Это экспорт всех чатов. Экспортируйте один чат (Export chat history) и повторите."
        )

    messages = data.get("messages")
    if not isinstance(messages, list):
        raise ChatstyleError(f"Файл {path} не похож на экспорт Telegram: нет списка messages.")
    return messages


def read_tg_export(path: Path, sender: str) -> list[str]:
    """Вернуть тексты сообщений ``sender`` из JSON‑экспорта Telegram Desktop.

    Параметры
    ----------
    path: pathlib.Path
        Путь к файлу экспорта.
    sender: str
        Идентификатор отправителя (имя, ``from_id`` или числовой id).

    Возвращаемое значение
    ----------------------
    list[str]
        Список сообщений в порядке их появления. Пустые сообщения
        (после ``strip``) отбрасываются. Если отправитель найден, но
        текстовых сообщений нет, возвращается пустой список.

    Исключения
    ----------
    ChatstyleError
        При проблемах чтения файла, парсинга JSON, неверном формате
        экспорта или отсутствии указанного отправителя.
    """
    messages = _load_messages(path)

    author_counter: Counter[str] = Counter()
    result: list[str] = []
    sender_seen = False

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("type") != "message":
            continue
        if "forwarded_from" in msg:
            # Пересланные сообщения не учитываются ни в результате,
            # ни в проверке наличия отправителя.
            continue

        author = msg.get("from")
        if isinstance(author, str) and author:
            author_counter[author] += 1

        if _matches(msg, sender):
            sender_seen = True
            flat = _flatten_text(msg.get("text"))
            if flat.strip():
                result.append(flat)

    if not sender_seen:
        most_common = ", ".join(f"{name} ({cnt})" for name, cnt in author_counter.most_common(10))
        raise ChatstyleError(f"Отправитель «{sender}» не найден в {path}. Есть: {most_common}.")

    return result


def read_tg_export_by_sender(path: Path) -> dict[str, list[str]]:
    """Тексты всех отправителей группового чата: ключ — ``from_id`` (или имя, если id нет).

    Правила те же, что у ``read_tg_export``: пересланные, сервисные и пустые сообщения
    пропускаются, порядок сообщений сохраняется. Ключи идут в порядке первого появления.
    """
    result: dict[str, list[str]] = {}
    for msg in _load_messages(path):
        if not isinstance(msg, dict) or msg.get("type") != "message" or "forwarded_from" in msg:
            continue
        key = msg.get("from_id") or msg.get("from")
        if not isinstance(key, str) or not key:
            continue
        flat = _flatten_text(msg.get("text"))
        if flat.strip():
            result.setdefault(key, []).append(flat)
    return result
