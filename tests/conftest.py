import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def isolated_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    """Тесты не трогают реальные файлы пользователя, ключи и внешнюю сеть."""
    home: Path = tmp_path_factory.mktemp("chatstyle_home")
    monkeypatch.setenv("CHATSTYLE_HOME", str(home))
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    # CI и пользователи принудительно включают цвет; тестам нужен чистый текст
    for name in ("FORCE_COLOR", "PY_COLORS", "FORCE_TERMINAL", "GITHUB_ACTIONS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("typer.rich_utils.FORCE_TERMINAL", None)

    original_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: object) -> None:
        host = address[0] if isinstance(address, tuple) and address else address
        if host not in _LOOPBACK:
            raise RuntimeError(f"Сеть в тестах запрещена: попытка подключения к {host!r}")
        original_connect(self, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    from chatstyle import securestore

    securestore.reset_default_vault(None)  # общее хранилище не переходит из теста в тест
    securestore.set_password_prompt(None)
    yield
    securestore.reset_default_vault(None)
    securestore.set_password_prompt(None)
