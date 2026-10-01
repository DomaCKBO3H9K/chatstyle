import json
import socket
from pathlib import Path

import pytest
from chatstyle import paths
from chatstyle.cache import load_cached, store_cached
from chatstyle.config import TelegramCredentials, load_telegram_credentials, parse_env_file
from chatstyle.errors import ChatstyleError

# --- paths ---


def test_data_dir_uses_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHATSTYLE_HOME", str(tmp_path))
    assert paths.data_dir() == tmp_path
    assert paths.env_file() == tmp_path / ".env"
    assert paths.session_file() == tmp_path / "telegram.session"
    assert paths.cache_dir() == tmp_path / "cache"


def test_data_dir_windows_uses_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHATSTYLE_HOME")
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.data_dir() == tmp_path / "chatstyle"


def test_data_dir_posix_uses_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHATSTYLE_HOME")
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert paths.data_dir() == tmp_path / "chatstyle"


# --- .env и ключи ---


def test_parse_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# комментарий\n"
        "TELEGRAM_API_ID=123\n"
        'TELEGRAM_API_HASH = "abc def"\n'
        "export OTHER='x'\n"
        "BROKEN LINE\n"
        "\n"
        "=novalue\n",
        encoding="utf-8",
    )
    assert parse_env_file(env) == {
        "TELEGRAM_API_ID": "123",
        "TELEGRAM_API_HASH": "abc def",
        "OTHER": "x",
    }


def test_parse_env_file_missing_returns_empty(tmp_path: Path) -> None:
    assert parse_env_file(tmp_path / "nope.env") == {}


def test_credentials_from_environment() -> None:
    creds = load_telegram_credentials(
        {"TELEGRAM_API_ID": "42", "TELEGRAM_API_HASH": "hash"}, env_files=()
    )
    assert creds == TelegramCredentials(api_id=42, api_hash="hash")


def test_credentials_from_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_API_ID=7\nTELEGRAM_API_HASH=h7\n", encoding="utf-8")
    creds = load_telegram_credentials({}, env_files=(env,))
    assert (creds.api_id, creds.api_hash) == (7, "h7")


def test_environment_wins_over_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=file\n", encoding="utf-8")
    creds = load_telegram_credentials(
        {"TELEGRAM_API_ID": "2", "TELEGRAM_API_HASH": "environ"}, env_files=(env,)
    )
    assert (creds.api_id, creds.api_hash) == (2, "environ")


def test_credentials_default_search_uses_data_dir_env() -> None:
    paths.env_file().parent.mkdir(parents=True, exist_ok=True)
    paths.env_file().write_text("TELEGRAM_API_ID=5\nTELEGRAM_API_HASH=h5\n", encoding="utf-8")
    creds = load_telegram_credentials({})
    assert creds.api_id == 5


def test_credentials_missing_explains_where_to_get() -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        load_telegram_credentials({}, env_files=())
    assert "my.telegram.org" in str(exc_info.value)


def test_credentials_non_numeric_id() -> None:
    with pytest.raises(ChatstyleError) as exc_info:
        load_telegram_credentials({"TELEGRAM_API_ID": "abc", "TELEGRAM_API_HASH": "h"}, ())
    assert "числом" in str(exc_info.value)


def test_api_hash_is_not_in_repr() -> None:
    creds = TelegramCredentials(api_id=1, api_hash="supersecret")
    assert "supersecret" not in repr(creds)


# --- кэш ---


def test_cache_roundtrip(tmp_path: Path) -> None:
    store_cached("@chat", "@user", 100, ["привет", "мир"], tmp_path)
    assert load_cached("@chat", "@user", 100, tmp_path) == ["привет", "мир"]


def test_cache_key_depends_on_chat_sender_and_limit(tmp_path: Path) -> None:
    store_cached("@chat", "@user", 100, ["a"], tmp_path)
    assert load_cached("@chat", "@user", 200, tmp_path) is None
    assert load_cached("@chat", "@other", 100, tmp_path) is None
    assert load_cached("@other", "@user", 100, tmp_path) is None


def test_cache_miss_and_corrupt_file(tmp_path: Path) -> None:
    assert load_cached("@c", "@u", 1, tmp_path) is None
    store_cached("@c", "@u", 1, ["x"], tmp_path)
    (file,) = tmp_path.glob("*.json")
    file.write_text("{не json", encoding="utf-8")
    assert load_cached("@c", "@u", 1, tmp_path) is None
    file.write_text(json.dumps({"version": 99, "messages": ["x"]}), encoding="utf-8")
    assert load_cached("@c", "@u", 1, tmp_path) is None
    file.write_text(json.dumps({"version": 1, "messages": [1, 2]}), encoding="utf-8")
    assert load_cached("@c", "@u", 1, tmp_path) is None


def test_cache_default_directory_is_data_dir_cache() -> None:
    store_cached("@c", "@u", 1, ["x"])
    assert len(list(paths.cache_dir().glob("*.json"))) == 1
    assert load_cached("@c", "@u", 1) == ["x"]


def test_cache_write_failure_is_not_fatal(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    store_cached("@c", "@u", 1, ["x"], blocker / "sub")


# --- защита от сети ---


def test_network_is_blocked() -> None:
    sock = socket.socket()
    try:
        with pytest.raises(RuntimeError, match="Сеть в тестах запрещена"):
            sock.connect(("example.com", 80))
    finally:
        sock.close()
