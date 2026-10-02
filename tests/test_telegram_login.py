"""Тесты для TelegramLogin без сети."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from chatstyle.collectors.telegram_login import (
    STEP_LOGGED_IN,
    STEP_LOGGED_OUT,
    STEP_NEED_CODE,
    STEP_NEED_PASSWORD,
    TelegramLogin,
    TelegramLoginError,
    account_file,
)
from chatstyle.config import TelegramCredentials, load_telegram_credentials
from chatstyle.errors import ChatstyleError
from telethon import errors

CREDS = TelegramCredentials(api_id=1, api_hash="a" * 32)


class FakeClient:
    """Заглушка TelegramClient для тестов."""

    def __init__(
        self,
        *,
        authorized: bool = False,
        connect_error: Exception | None = None,
        send_code_error: Exception | None = None,
        sign_in_script: list | None = None,
        me: SimpleNamespace | None = None,
    ) -> None:
        self.authorized = authorized
        self.connect_error = connect_error
        self.send_code_error = send_code_error
        self.sign_in_script = sign_in_script or []
        self.sign_in_calls: list[dict] = []
        self.calls: list[str] = []
        self.phone: str | None = None
        self.phone_code_hash: str | None = None
        self.logged_out = False
        self.disconnected = False
        self.me = me or SimpleNamespace(
            first_name="Иван", last_name="Петров", username="ivan", id=7
        )
        self._sign_in_index = 0

    async def connect(self) -> None:
        self.calls.append("connect")
        if self.connect_error:
            raise self.connect_error

    async def disconnect(self) -> None:
        self.calls.append("disconnect")
        self.disconnected = True

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def send_code_request(self, phone: str) -> SimpleNamespace:
        self.calls.append("send_code_request")
        self.phone = phone
        if self.send_code_error:
            raise self.send_code_error
        result = SimpleNamespace(phone_code_hash="HASH")
        self.phone_code_hash = "HASH"
        return result

    async def sign_in(
        self,
        phone: str | None = None,
        code: str | None = None,
        phone_code_hash: str | None = None,
        password: str | None = None,
    ) -> SimpleNamespace:
        self.calls.append("sign_in")
        call_info = {
            "phone": phone,
            "code": code,
            "phone_code_hash": phone_code_hash,
            "password": password,
        }
        self.sign_in_calls.append(call_info)

        if self._sign_in_index < len(self.sign_in_script):
            item = self.sign_in_script[self._sign_in_index]
            self._sign_in_index += 1
            if isinstance(item, Exception):
                raise item
            # "ok" - успех
            self.authorized = True
        return self.me

    async def get_me(self) -> SimpleNamespace:
        self.calls.append("get_me")
        return self.me

    async def log_out(self) -> None:
        self.calls.append("log_out")
        self.logged_out = True


def _create_session_file(session_path: str) -> Path:
    """Создаёт файл сессии, имитируя Telethon."""
    session_file = Path(session_path)
    if not session_file.suffix:
        session_file = session_file.with_suffix(".session")
    session_file.parent.mkdir(parents=True, exist_ok=True)
    if not session_file.exists():
        session_file.write_text("x", encoding="utf-8")
    return session_file


def make_factory(client: FakeClient, session_path: Path):
    """Создаёт фабрику, которая имитирует создание файла сессии."""

    def factory(session: str, api_id: int, api_hash: str, **kwargs):
        _create_session_file(session)
        return client

    return factory


def make_factory_with_clients(clients: list[FakeClient], session_path: Path):
    """Фабрика, возвращающая разные клиенты по вызовам."""
    call_count = [0]

    def factory(session: str, api_id: int, api_hash: str, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        client = clients[idx] if idx < len(clients) else clients[-1]
        _create_session_file(session)
        return client

    return factory


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Изолированное окружение: временная директория, без переменных API."""
    monkeypatch.setenv("CHATSTYLE_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    return tmp_path


# 1. status() без сессии
def test_status_logged_out_without_session(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=lambda *a, **kw: None,
    )
    state = login.status()
    assert state.step == STEP_LOGGED_OUT
    assert state.name is None
    assert state.has_keys is True

    def bad_loader():
        raise ChatstyleError("no keys")

    login2 = TelegramLogin(
        credentials_loader=bad_loader,
        session=session_path,
        client_factory=lambda *a, **kw: None,
    )
    state2 = login2.status()
    assert state2.step == STEP_LOGGED_OUT
    assert state2.has_keys is False


# 2. Полный вход без 2FA
def test_full_login_without_2fa(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient()
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )

    state = login.begin("+79001234567")
    assert state.step == STEP_NEED_CODE
    assert client.calls == ["connect", "send_code_request"]
    assert client.phone == "+79001234567"

    state = login.submit_code("12 345")
    assert state.step == STEP_LOGGED_IN
    assert state.name == "Иван Петров"
    assert client.sign_in_calls[-1] == {
        "phone": "+79001234567",
        "code": "12345",
        "phone_code_hash": "HASH",
        "password": None,
    }
    assert client.disconnected is True

    state = login.status()
    assert state.step == STEP_LOGGED_IN
    assert state.name == "Иван Петров"

    account_path = account_file()
    assert account_path.exists()
    assert account_path.read_text(encoding="utf-8") == "Иван Петров"


# 3. Вход с 2FA
def test_login_with_2fa(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient(sign_in_script=[errors.SessionPasswordNeededError(request=None), "ok"])
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )

    login.begin("+79001234567")
    state = login.submit_code("123")
    assert state.step == STEP_NEED_PASSWORD

    state_mid = login.status()
    assert state_mid.step == STEP_NEED_PASSWORD

    state = login.submit_password("secret")
    assert state.step == STEP_LOGGED_IN
    assert client.sign_in_calls[-1]["password"] == "secret"


# 4. Неверный код
def test_invalid_code(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient(sign_in_script=[errors.PhoneCodeInvalidError(request=None), "ok"])
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )
    login.begin("+79001234567")

    with pytest.raises(TelegramLoginError) as exc_info:
        login.submit_code("999")
    assert exc_info.value.code == "code_invalid"

    state = login.submit_code("123")
    assert state.step == STEP_LOGGED_IN


# 5. Устаревший код
def test_expired_code(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient(sign_in_script=[errors.PhoneCodeExpiredError(request=None)])
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )
    login.begin("+79001234567")

    with pytest.raises(TelegramLoginError) as exc_info:
        login.submit_code("123")
    assert exc_info.value.code == "code_expired"

    state = login.status()
    assert state.step == STEP_LOGGED_OUT
    assert not session_path.exists()

    with pytest.raises(TelegramLoginError) as exc_info2:
        login.submit_code("123")
    assert exc_info2.value.code == "login_not_started"


# 6. Неверный пароль 2FA
def test_invalid_2fa_password(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient(
        sign_in_script=[
            errors.SessionPasswordNeededError(request=None),
            errors.PasswordHashInvalidError(request=None),
            "ok",
        ]
    )
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )
    login.begin("+79001234567")
    login.submit_code("123")

    with pytest.raises(TelegramLoginError) as exc_info:
        login.submit_password("wrong")
    assert exc_info.value.code == "password_invalid"

    state = login.status()
    assert state.step == STEP_NEED_PASSWORD

    state = login.submit_password("secret")
    assert state.step == STEP_LOGGED_IN


# 7. Ошибки begin
@pytest.mark.parametrize(
    "error, expected_code, expected_params",
    [
        (errors.PhoneNumberInvalidError(request=None), "phone_invalid", {}),
        (errors.ApiIdInvalidError(request=None), "api_invalid", {}),
        (errors.FloodWaitError(request=None, capture=90), "flood_wait", {"minutes": "2"}),
        (ConnectionError("x"), "network", {}),
    ],
)
def test_begin_errors(isolated, error, expected_code, expected_params):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient(connect_error=error)
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )

    with pytest.raises(TelegramLoginError) as exc_info:
        login.begin("+79001234567")
    assert exc_info.value.code == expected_code
    for k, v in expected_params.items():
        assert exc_info.value.params.get(k) == v

    assert not session_path.exists()
    assert login.status().step == STEP_LOGGED_OUT


def test_begin_empty_phone(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient()
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )

    with pytest.raises(TelegramLoginError) as exc_info:
        login.begin("")
    assert exc_info.value.code == "phone_invalid"
    assert client.calls == []


def test_begin_missing_keys(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient()
    factory = make_factory(client, session_path)

    def bad_loader():
        raise ChatstyleError("no keys")

    login = TelegramLogin(
        credentials_loader=bad_loader,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )

    with pytest.raises(TelegramLoginError) as exc_info:
        login.begin("+79001234567")
    assert exc_info.value.code == "keys_missing"


# 8. begin, когда сессия уже авторизована
def test_begin_already_authorized(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient(authorized=True)
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )

    state = login.begin("+79001234567")
    assert state.step == STEP_LOGGED_IN
    assert "send_code_request" not in client.calls


# 9. Защита существующей сессии
def test_session_preserved_on_error(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text("existing session", encoding="utf-8")

    client = FakeClient(connect_error=ConnectionError("x"))
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )

    with pytest.raises(TelegramLoginError):
        login.begin("+79001234567")

    assert session_path.exists()
    assert session_path.read_text() == "existing session"


# 10. cancel() после begin
def test_cancel_after_begin(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient()
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )
    login.begin("+79001234567")

    state = login.cancel()
    assert state.step == STEP_LOGGED_OUT
    assert client.disconnected is True
    assert not session_path.exists()


# 11. Бездействие (idle timeout)
def test_idle_timeout(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient()
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=0.2,
    )
    login.begin("+79001234567")

    for _ in range(60):  # максимум 3 секунды при sleep(0.05)
        state = login.status()
        if state.step == STEP_LOGGED_OUT:
            break
        time.sleep(0.05)
    else:
        pytest.fail("Idle timeout did not fire")

    assert state.step == STEP_LOGGED_OUT
    assert client.disconnected is True


# 12. logout()
def test_logout_after_login(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client = FakeClient(sign_in_script=["ok"])
    factory = make_factory(client, session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )
    login.begin("+79001234567")
    login.submit_code("123")

    state = login.logout()
    assert state.step == STEP_LOGGED_OUT
    assert state.remote_failed is False
    assert client.logged_out is True
    assert not session_path.exists()
    assert not account_file().exists()


def test_logout_with_network_error(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client1 = FakeClient()
    client2 = FakeClient(connect_error=ConnectionError("x"))
    factory = make_factory_with_clients([client1, client2], session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )
    login.begin("+79001234567")
    login.submit_code("123")

    state = login.logout()
    assert state.step == STEP_LOGGED_OUT
    assert state.remote_failed is True
    assert not session_path.exists()
    assert not account_file().exists()


# 13. save_keys
def test_save_keys(isolated):
    tmp_path = isolated
    env_path = tmp_path / ".env"
    env_path.write_text(
        "FOO=bar\n# заметка\nTELEGRAM_API_ID=1\nexport TELEGRAM_API_HASH=old\n",
        encoding="utf-8",
    )

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=tmp_path / "telegram.session",
        client_factory=lambda *a, **kw: None,
    )
    login.save_keys("123", "b" * 32)

    content = env_path.read_text(encoding="utf-8")
    assert "TELEGRAM_API_ID=123" in content
    assert "TELEGRAM_API_HASH=" + "b" * 32 in content
    assert "FOO=bar" in content
    assert "# заметка" in content
    assert "TELEGRAM_API_ID=1" not in content.splitlines()
    assert "TELEGRAM_API_HASH=old" not in content

    creds = load_telegram_credentials(environ={}, env_files=(env_path,))
    assert creds.api_id == 123
    assert creds.api_hash == "b" * 32


@pytest.mark.parametrize(
    "api_id, api_hash",
    [
        ("abc", "a" * 32),
        ("0", "a" * 32),
        ("-5", "a" * 32),
        ("123", "short"),
        ("123", "g" * 32),  # не hex
    ],
)
def test_save_keys_invalid(isolated, api_id, api_hash):
    tmp_path = isolated
    env_path = tmp_path / ".env"
    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=tmp_path / "telegram.session",
        client_factory=lambda *a, **kw: None,
    )

    with pytest.raises(TelegramLoginError) as exc_info:
        login.save_keys(api_id, api_hash)
    assert exc_info.value.code == "keys_invalid"
    assert not env_path.exists()


# 14. Секреты не утекают
def test_secrets_not_leaked(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"

    # Неверный код
    client1 = FakeClient(sign_in_script=[errors.PhoneCodeInvalidError(request=None)])
    factory1 = make_factory(client1, session_path)
    login1 = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory1,
        idle_seconds=60,
    )
    login1.begin("+79001234567")
    try:
        login1.submit_code("12345")
    except TelegramLoginError as e:
        assert "12345" not in str(e)
        assert "a" * 32 not in str(e)
        for v in e.params.values():
            assert "12345" not in str(v)
            assert "a" * 32 not in str(v)

    # Неверный пароль 2FA
    client2 = FakeClient(
        sign_in_script=[
            errors.SessionPasswordNeededError(request=None),
            errors.PasswordHashInvalidError(request=None),
        ]
    )
    factory2 = make_factory(client2, session_path)
    login2 = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory2,
        idle_seconds=60,
    )
    login2.begin("+79001234567")
    login2.submit_code("123")
    try:
        login2.submit_password("secret")
    except TelegramLoginError as e:
        assert "secret" not in str(e)
        assert "a" * 32 not in str(e)
        for v in e.params.values():
            assert "secret" not in str(v)
            assert "a" * 32 not in str(v)

    # Ошибки begin
    client3 = FakeClient(connect_error=errors.FloodWaitError(request=None, capture=90))
    factory3 = make_factory(client3, session_path)
    login3 = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory3,
        idle_seconds=60,
    )
    try:
        login3.begin("+79001234567")
    except TelegramLoginError as e:
        assert "a" * 32 not in str(e)
        for v in e.params.values():
            assert "a" * 32 not in str(v)


# 15. Параллельность
def test_parallel_begin(isolated):
    tmp_path = isolated
    session_path = tmp_path / "telegram.session"
    client1 = FakeClient()
    client2 = FakeClient()

    factory = make_factory_with_clients([client1, client2], session_path)

    login = TelegramLogin(
        credentials_loader=lambda: CREDS,
        session=session_path,
        client_factory=factory,
        idle_seconds=60,
    )

    login.begin("+79001234567")
    login.begin("+79001234568")

    assert client1.disconnected is True
    assert client2.calls == ["connect", "send_code_request"]
