from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from chatstyle import paths
from chatstyle.collectors import CollectOptions, collect
from chatstyle.collectors import telegram as tg
from chatstyle.collectors.telegram import (
    TelegramSource,
    TelethonFetcher,
    parse_telegram_spec,
    read_telegram,
)
from chatstyle.config import TelegramCredentials
from chatstyle.errors import ChatstyleError
from telethon import errors

CREDS = TelegramCredentials(api_id=1, api_hash="hash")
USER = SimpleNamespace(id=2, name="user")
GROUP = SimpleNamespace(id=100, name="group")


def msg(
    text: str, sender_id: int = 2, fwd: object | None = None, action: object | None = None
) -> SimpleNamespace:
    return SimpleNamespace(message=text, sender_id=sender_id, fwd_from=fwd, action=action)


NEWEST_FIRST = [
    msg("c"),
    msg("пересланное", fwd=object()),
    msg("чужое", sender_id=9),
    msg("   "),
    msg("служебное", action=object()),
    msg("a"),
]


class FakeClient:
    """Подмена TelegramClient: ни сети, ни файлов."""

    def __init__(
        self,
        entities: dict[Any, Any],
        messages: list[SimpleNamespace] | None = None,
        *,
        hidden: dict[Any, Any] | None = None,
        authorized: bool = True,
        connect_error: Exception | None = None,
        iter_error: Exception | None = None,
        me: SimpleNamespace | None = None,
    ) -> None:
        self.entities = dict(entities)
        self.hidden = dict(hidden or {})
        self.messages = messages or []
        self.authorized = authorized
        self.connect_error = connect_error
        self.iter_error = iter_error
        self.me = me or SimpleNamespace(first_name="Иван", last_name="Петров", username="ivan")
        self.calls: list[str] = []
        self.iter_kwargs: dict[str, Any] = {}

    async def connect(self) -> None:
        self.calls.append("connect")
        if self.connect_error:
            raise self.connect_error

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def get_entity(self, peer: Any) -> Any:
        self.calls.append(f"get_entity:{peer}")
        if peer in self.entities:
            return self.entities[peer]
        raise ValueError("not found")

    async def get_dialogs(self) -> None:
        self.calls.append("get_dialogs")
        self.entities.update(self.hidden)

    async def iter_messages(self, chat: Any, **kwargs: Any) -> AsyncIterator[SimpleNamespace]:
        self.iter_kwargs = {"chat": chat, **kwargs}
        if self.iter_error:
            raise self.iter_error
        for message in self.messages[: kwargs.get("limit")]:
            yield message

    async def start(self) -> None:
        self.calls.append("start")

    async def get_me(self) -> SimpleNamespace:
        return self.me

    async def disconnect(self) -> None:
        self.calls.append("disconnect")


def make_fetcher(client: FakeClient, tmp_path: Path) -> tuple[TelethonFetcher, list[tuple]]:
    factory_calls: list[tuple] = []

    def factory(session: str, api_id: int, api_hash: str, **kwargs: Any) -> FakeClient:
        factory_calls.append((session, api_id, api_hash, kwargs))
        return client

    fetcher = TelethonFetcher(CREDS, tmp_path / "sub" / "telegram.session", factory)
    return fetcher, factory_calls


# --- разбор источника ---


@pytest.mark.parametrize(
    ("value", "chat", "sender"),
    [
        ("@friend", "@friend", "@friend"),
        ("@group#@user", "@group", "@user"),
        ("  @g # 123 ", "@g", "123"),
        ("-100500#42", "-100500", "42"),
    ],
)
def test_parse_telegram_spec(value: str, chat: str, sender: str) -> None:
    assert parse_telegram_spec(value) == TelegramSource(chat=chat, sender=sender)


@pytest.mark.parametrize("value", ["#@user", "@group#", " ", "#"])
def test_parse_telegram_spec_invalid(value: str) -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        parse_telegram_spec(value)
    assert "tg:@friend" in str(exc_info.value)


# --- read_telegram: кэш, лимит, уведомления ---


class FakeFetcher:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.calls: list[tuple[TelegramSource, int]] = []

    def fetch(self, source: TelegramSource, limit: int) -> list[str]:
        self.calls.append((source, limit))
        return self.messages


def test_read_telegram_fetches_then_uses_cache(tmp_path: Path) -> None:
    fetcher = FakeFetcher(["привет", "мир"])
    notes: list[str] = []
    first = read_telegram(
        "@g#@u", limit=50, fetcher=fetcher, cache_directory=tmp_path, notify=notes.append
    )
    second = read_telegram(
        "@g#@u", limit=50, fetcher=fetcher, cache_directory=tmp_path, notify=notes.append
    )
    assert first == second == ["привет", "мир"]
    assert fetcher.calls == [(TelegramSource("@g", "@u"), 50)]
    assert "загружено из Telegram 2" in notes[0]
    assert "из кэша" in notes[1]


def test_read_telegram_refresh_ignores_cache(tmp_path: Path) -> None:
    fetcher = FakeFetcher(["a"])
    read_telegram("@u", fetcher=fetcher, cache_directory=tmp_path)
    read_telegram("@u", fetcher=fetcher, cache_directory=tmp_path, refresh=True)
    assert len(fetcher.calls) == 2


def test_read_telegram_limit_is_part_of_cache_key(tmp_path: Path) -> None:
    fetcher = FakeFetcher(["a"])
    read_telegram("@u", limit=10, fetcher=fetcher, cache_directory=tmp_path)
    read_telegram("@u", limit=20, fetcher=fetcher, cache_directory=tmp_path)
    assert [limit for _, limit in fetcher.calls] == [10, 20]


def test_read_telegram_invalid_limit(tmp_path: Path) -> None:
    with pytest.raises(ChatstyleError):
        read_telegram("@u", limit=0, fetcher=FakeFetcher(["a"]), cache_directory=tmp_path)


def test_read_telegram_empty_result_is_error_and_not_cached(tmp_path: Path) -> None:
    fetcher = FakeFetcher([])
    with pytest.raises(ChatstyleError) as exc_info:
        read_telegram("@g#@u", fetcher=fetcher, cache_directory=tmp_path)
    assert "не найдено текстовых сообщений" in str(exc_info.value)
    assert not list(tmp_path.glob("*.json"))


# --- TelethonFetcher на подменённом клиенте ---


def test_fetch_filters_and_returns_chronological_order(tmp_path: Path) -> None:
    client = FakeClient({"@g": GROUP, "@u": USER}, NEWEST_FIRST)
    fetcher, factory_calls = make_fetcher(client, tmp_path)
    result = fetcher.fetch(TelegramSource("@g", "@u"), 100)
    assert result == ["a", "c"]
    assert client.iter_kwargs == {"chat": GROUP, "limit": 100, "from_user": USER}
    assert client.calls[-1] == "disconnect"
    session, api_id, api_hash, kwargs = factory_calls[0]
    assert (api_id, api_hash) == (1, "hash")
    assert kwargs == {"flood_sleep_threshold": tg.FLOOD_SLEEP_THRESHOLD}
    assert Path(session).parent.is_dir()


def test_fetch_personal_chat_resolves_once(tmp_path: Path) -> None:
    client = FakeClient({"@u": USER}, NEWEST_FIRST)
    fetcher, _ = make_fetcher(client, tmp_path)
    fetcher.fetch(TelegramSource("@u", "@u"), 10)
    assert client.calls.count("get_entity:@u") == 1
    assert client.iter_kwargs["chat"] is USER
    assert client.iter_kwargs["from_user"] is USER


def test_fetch_respects_limit(tmp_path: Path) -> None:
    client = FakeClient({"@u": USER}, NEWEST_FIRST)
    fetcher, _ = make_fetcher(client, tmp_path)
    assert fetcher.fetch(TelegramSource("@u", "@u"), 1) == ["c"]


def test_fetch_numeric_id_loads_dialogs_when_unknown(tmp_path: Path) -> None:
    client = FakeClient({}, NEWEST_FIRST, hidden={42: USER})
    fetcher, _ = make_fetcher(client, tmp_path)
    assert fetcher.fetch(TelegramSource("42", "42"), 10) == ["a", "c"]
    assert client.calls.count("get_dialogs") == 1


def test_fetch_unknown_username(tmp_path: Path) -> None:
    client = FakeClient({}, [])
    fetcher, _ = make_fetcher(client, tmp_path)
    with pytest.raises(ChatstyleError) as exc_info:
        fetcher.fetch(TelegramSource("@nobody", "@nobody"), 10)
    assert "Не удалось найти «@nobody»" in str(exc_info.value)
    assert "get_dialogs" not in client.calls
    assert client.calls[-1] == "disconnect"


def test_fetch_unknown_numeric_id_after_dialogs(tmp_path: Path) -> None:
    client = FakeClient({}, [])
    fetcher, _ = make_fetcher(client, tmp_path)
    with pytest.raises(ChatstyleError):
        fetcher.fetch(TelegramSource("7", "7"), 10)
    assert "get_dialogs" in client.calls


def test_fetch_requires_login(tmp_path: Path) -> None:
    client = FakeClient({"@u": USER}, NEWEST_FIRST, authorized=False)
    fetcher, _ = make_fetcher(client, tmp_path)
    with pytest.raises(ChatstyleError) as exc_info:
        fetcher.fetch(TelegramSource("@u", "@u"), 10)
    assert "chatstyle login" in str(exc_info.value)
    assert client.calls[-1] == "disconnect"


def test_fetch_flood_wait_becomes_readable_error(tmp_path: Path) -> None:
    error = errors.FloodWaitError(request=None, capture=90)
    client = FakeClient({"@u": USER}, [], iter_error=error)
    fetcher, _ = make_fetcher(client, tmp_path)
    with pytest.raises(ChatstyleError) as exc_info:
        fetcher.fetch(TelegramSource("@u", "@u"), 10)
    assert "подождать около 2 мин" in str(exc_info.value)
    assert client.calls[-1] == "disconnect"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (errors.UsernameNotOccupiedError(request=None), "не найден"),
        (errors.ChannelPrivateError(request=None), "Нет доступа"),
        (ConnectionError("down"), "Нет соединения с Telegram"),
        (TimeoutError("slow"), "Нет соединения с Telegram"),
    ],
)
def test_fetch_translates_errors(error: Exception, expected: str, tmp_path: Path) -> None:
    client = FakeClient({"@u": USER}, [], connect_error=error)
    fetcher, _ = make_fetcher(client, tmp_path)
    with pytest.raises(ChatstyleError) as exc_info:
        fetcher.fetch(TelegramSource("@u", "@u"), 10)
    assert expected in str(exc_info.value)


def test_fetch_does_not_hide_unexpected_errors(tmp_path: Path) -> None:
    client = FakeClient({"@u": USER}, [], connect_error=KeyError("bug"))
    fetcher, _ = make_fetcher(client, tmp_path)
    with pytest.raises(KeyError):
        fetcher.fetch(TelegramSource("@u", "@u"), 10)


def test_fetch_without_credentials_explains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    fetcher = TelethonFetcher(session=tmp_path / "s.session")
    with pytest.raises(ChatstyleError) as exc_info:
        fetcher.fetch(TelegramSource("@u", "@u"), 10)
    assert "my.telegram.org" in str(exc_info.value)


def test_default_session_is_in_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient({"@u": USER}, NEWEST_FIRST)
    sessions: list[str] = []

    def factory(session: str, *_args: Any, **_kwargs: Any) -> FakeClient:
        sessions.append(session)
        return client

    TelethonFetcher(CREDS, client_factory=factory).fetch(TelegramSource("@u", "@u"), 5)
    assert sessions == [str(paths.session_file())]


def test_login_returns_account_name(tmp_path: Path) -> None:
    client = FakeClient({})
    fetcher, _ = make_fetcher(client, tmp_path)
    assert fetcher.login() == "Иван Петров"
    assert client.calls == ["start", "disconnect"]


def test_login_falls_back_to_username(tmp_path: Path) -> None:
    client = FakeClient({}, me=SimpleNamespace(first_name=None, last_name=None, username="ivan"))
    fetcher, _ = make_fetcher(client, tmp_path)
    assert fetcher.login() == "ivan"


# --- collect и tg: ---


def test_collect_tg_uses_options(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher = FakeFetcher(["привет"])
    monkeypatch.setattr(tg, "TelethonFetcher", lambda: fetcher)
    notes: list[str] = []
    options = CollectOptions(limit=5, notify=notes.append)
    assert collect("tg:@g#@u", options) == ["привет"]
    assert fetcher.calls == [(TelegramSource("@g", "@u"), 5)]
    assert notes


def test_collect_tg_without_keys_is_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ChatstyleError) as exc_info:
        collect("tg:@user")
    assert "my.telegram.org" in str(exc_info.value)
