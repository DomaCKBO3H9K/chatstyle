"""Сбор сообщений из Telegram через Telethon.

Обращение к сети происходит только здесь и только по явной команде пользователя
(`chatstyle login` и `compare` с источником `tg:`). Остальная логика (разбор источника,
кэш, фильтрация сообщений) не зависит от сети и проверяется тестами с подменой клиента.
"""

import asyncio
import math
import os
import socket
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from chatstyle.cache import load_cached, store_cached
from chatstyle.config import TelegramCredentials, load_telegram_credentials
from chatstyle.errors import ChatstyleError, CodedError
from chatstyle.paths import session_file

DEFAULT_LIMIT = 3000
FLOOD_SLEEP_THRESHOLD = 300

_SPEC_HELP = "Укажите источник как tg:@friend (личная переписка) или tg:@группа#@человек."

ClientFactory = Callable[..., Any]
Notify = Callable[[str], None]


@dataclass(frozen=True)
class TelegramSource:
    """Чат и отправитель, чьи сообщения нужно собрать."""

    chat: str
    sender: str


class Fetcher(Protocol):
    """Всё, что умеет достать сообщения отправителя из Telegram."""

    def fetch(self, source: TelegramSource, limit: int) -> list[str]: ...


def parse_telegram_spec(value: str) -> TelegramSource:
    """Разобрать «чат#отправитель» или «пользователь» (личная переписка)."""
    chat, sep, sender = value.rpartition("#")
    if not sep:
        chat = sender = value
    chat, sender = chat.strip(), sender.strip()
    if not chat or not sender:
        raise ChatstyleError(f"Некорректный источник tg:{value}. {_SPEC_HELP}")
    return TelegramSource(chat=chat, sender=sender)


def read_telegram(
    value: str,
    *,
    limit: int = DEFAULT_LIMIT,
    refresh: bool = False,
    notify: Notify | None = None,
    fetcher: Fetcher | None = None,
    cache_directory: Path | None = None,
) -> list[str]:
    """Вернуть сообщения отправителя: из кэша или из Telegram."""
    source = parse_telegram_spec(value)
    if limit < 1:
        raise ChatstyleError("Лимит сообщений должен быть не меньше 1.")
    say = notify if notify is not None else (lambda _message: None)

    if not refresh:
        cached = load_cached(source.chat, source.sender, limit, cache_directory)
        if cached is not None:
            say(f"tg:{value}: {len(cached)} сообщений из кэша (обновить: --refresh)")
            return cached

    messages = (fetcher if fetcher is not None else TelethonFetcher()).fetch(source, limit)
    if not messages:
        raise ChatstyleError(
            f"В Telegram не найдено текстовых сообщений от «{source.sender}» "
            f"в чате «{source.chat}»."
        )
    store_cached(source.chat, source.sender, limit, messages, cache_directory)
    say(f"tg:{value}: загружено из Telegram {len(messages)} сообщений")
    return messages


def _telethon_client_factory(session: str, api_id: int, api_hash: str, **kwargs: Any) -> Any:
    from telethon import TelegramClient

    return TelegramClient(session, api_id, api_hash, **kwargs)


def _to_peer(reference: str) -> int | str:
    return int(reference) if reference.lstrip("-").isdigit() else reference


async def _resolve(client: Any, reference: str) -> Any:
    """Найти пользователя или чат; числовой id известен Telethon только после диалогов."""
    peer = _to_peer(reference)
    try:
        return await client.get_entity(peer)
    except ValueError:
        pass
    if isinstance(peer, int):
        await client.get_dialogs()
        try:
            return await client.get_entity(peer)
        except ValueError:
            pass
    raise ChatstyleError(f"Не удалось найти «{reference}» в Telegram.")


def _message_text(message: Any, sender_id: int | None) -> str | None:
    """Текст сообщения или None для пересланных, сервисных, чужих и пустых сообщений."""
    if getattr(message, "fwd_from", None) is not None:
        return None
    if getattr(message, "action", None) is not None:
        return None
    author = getattr(message, "sender_id", None)
    if sender_id is not None and author is not None and author != sender_id:
        return None
    text = getattr(message, "message", None)
    if not isinstance(text, str) or not text.strip():
        return None
    return text


def _translate_error(exc: Exception) -> ChatstyleError | None:
    """Превратить ошибку Telethon или сети в понятное сообщение; None — не наша ошибка."""
    from telethon import errors

    if isinstance(exc, errors.FloodWaitError):
        minutes = max(1, math.ceil(exc.seconds / 60))
        return CodedError(
            "flood_wait",
            f"Telegram просит подождать около {minutes} мин. Повторите запуск позже.",
            minutes=minutes,
        )
    if isinstance(exc, errors.ApiIdInvalidError):
        return CodedError(
            "api_invalid", "Telegram отклонил TELEGRAM_API_ID/TELEGRAM_API_HASH: проверьте их."
        )
    if isinstance(exc, errors.UsernameNotOccupiedError | errors.UsernameInvalidError):
        return CodedError(
            "chat_not_found", "Пользователь или чат с таким именем не найден в Telegram."
        )
    if isinstance(exc, errors.ChannelPrivateError | errors.ChatAdminRequiredError):
        return CodedError("chat_forbidden", "Нет доступа к этому чату или его истории.")
    if isinstance(exc, errors.RPCError):
        return ChatstyleError(f"Ошибка Telegram: {exc}")
    if isinstance(exc, sqlite3.OperationalError):
        return ChatstyleError("Файл сессии занят другим процессом chatstyle. Повторите позже.")
    if isinstance(exc, ConnectionError | TimeoutError | socket.gaierror):
        return CodedError("network", f"Нет соединения с Telegram: {exc}")
    return None


def _restrict_permissions(path: Path) -> None:
    """Сессия равна доступу к аккаунту: на POSIX оставляем права только владельцу."""
    if sys.platform != "win32":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


class TelethonFetcher:
    """Сетевой слой на Telethon. Клиент создаётся внутри цикла событий (нужно Python 3.14)."""

    def __init__(
        self,
        credentials: TelegramCredentials | None = None,
        session: Path | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._credentials = credentials
        self._session = session
        self._client_factory = client_factory

    def fetch(self, source: TelegramSource, limit: int) -> list[str]:
        """Собрать до limit сообщений отправителя в хронологическом порядке."""
        return self._run(self._fetch(source, limit))

    def login(self) -> str:
        """Интерактивный вход (телефон, код, пароль 2FA); возвращает имя аккаунта."""
        return self._run(self._login())

    def _run(self, coroutine: Any) -> Any:
        try:
            return asyncio.run(coroutine)
        except ChatstyleError:
            raise
        except Exception as exc:
            translated = _translate_error(exc)
            if translated is None:
                raise
            raise translated from exc

    def _session_path(self) -> Path:
        return self._session if self._session is not None else session_file()

    def _client(self) -> Any:
        credentials = self._credentials or load_telegram_credentials()
        session = self._session_path()
        session.parent.mkdir(parents=True, exist_ok=True)
        factory = self._client_factory or _telethon_client_factory
        return factory(
            str(session),
            credentials.api_id,
            credentials.api_hash,
            flood_sleep_threshold=FLOOD_SLEEP_THRESHOLD,
        )

    async def _fetch(self, source: TelegramSource, limit: int) -> list[str]:
        client = self._client()
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise CodedError(
                    "telegram_not_logged_in",
                    "Нет входа в Telegram. Выполните один раз: chatstyle login",
                )
            chat = await _resolve(client, source.chat)
            same = source.sender == source.chat
            sender = chat if same else await _resolve(client, source.sender)
            sender_id = getattr(sender, "id", None)
            collected: list[str] = []
            async for message in client.iter_messages(chat, limit=limit, from_user=sender):
                text = _message_text(message, sender_id)
                if text is not None:
                    collected.append(text)
        finally:
            await client.disconnect()
        collected.reverse()
        return collected

    async def _login(self) -> str:
        client = self._client()
        try:
            await client.start()
            me = await client.get_me()
        finally:
            await client.disconnect()
        _restrict_permissions(self._session_path())
        parts = [getattr(me, "first_name", None), getattr(me, "last_name", None)]
        name = " ".join(part for part in parts if part)
        return name or getattr(me, "username", None) or str(getattr(me, "id", ""))
