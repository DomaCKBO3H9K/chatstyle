"""TelegramLogin: настройка хранилища, шаги входа, выход, замок. Telegram подменён заглушкой."""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from chatstyle import paths
from chatstyle.collectors.telegram_login import (
    STEP_LOCKED,
    STEP_LOGGED_IN,
    STEP_LOGGED_OUT,
    STEP_NEED_CODE,
    STEP_NEED_PASSWORD,
    TelegramLogin,
    TelegramLoginError,
    account_file,
)
from chatstyle.config import TelegramCredentials
from chatstyle.errors import ChatstyleError
from chatstyle.securestore import MODE_DPAPI, MODE_MEMORY, MODE_PASSWORD, Vault, VaultError
from telethon import errors

CREDS = TelegramCredentials(api_id=1, api_hash="a" * 32)
HASH = "b" * 32
PASSWORD = "master password 123"
PHONE = "+79001234567"


def _valid_session_string() -> str:
    from telethon.crypto import AuthKey
    from telethon.sessions import StringSession

    session = StringSession()
    session.set_dc(2, "149.154.167.51", 443)
    session.auth_key = AuthKey(b"\x07" * 256)
    return session.save()


SAVED = _valid_session_string()


class FakeClient:
    """Заглушка TelegramClient: ни сети, ни файлов."""

    def __init__(
        self,
        *,
        authorized: bool = False,
        connect_error: Exception | None = None,
        send_code_error: Exception | None = None,
        sign_in_script: list | None = None,
    ) -> None:
        self.authorized = authorized
        self.connect_error = connect_error
        self.send_code_error = send_code_error
        self.sign_in_script = list(sign_in_script or [])
        self.sign_in_calls: list[dict] = []
        self.calls: list[str] = []
        self.phone: str | None = None
        self.logged_out = False
        self.disconnected = False
        self.sessions_seen: list[Any] = []
        self.me = SimpleNamespace(first_name="Иван", last_name="Петров", username="ivan", id=7)
        self.session = SimpleNamespace(save=lambda: SAVED)
        self.has_password: bool | Exception = True

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
        return SimpleNamespace(phone_code_hash="HASH")

    async def sign_in(
        self,
        phone: str | None = None,
        code: str | None = None,
        phone_code_hash: str | None = None,
        password: str | None = None,
    ) -> SimpleNamespace:
        self.calls.append("sign_in")
        self.sign_in_calls.append(
            {"phone": phone, "code": code, "phone_code_hash": phone_code_hash, "password": password}
        )
        if self.sign_in_script:
            item = self.sign_in_script.pop(0)
            if isinstance(item, Exception):
                raise item
            self.authorized = True
        return self.me

    async def __call__(self, request: object) -> SimpleNamespace:
        self.calls.append(type(request).__name__)
        if isinstance(self.has_password, Exception):
            raise self.has_password
        return SimpleNamespace(has_password=self.has_password)

    async def get_me(self) -> SimpleNamespace:
        return self.me

    async def log_out(self) -> None:
        self.calls.append("log_out")
        self.logged_out = True


def make_login(
    tmp_path: Path,
    client: FakeClient | None = None,
    *,
    mode: str | None = MODE_MEMORY,
    keys: bool = True,
    **kwargs: Any,
) -> tuple[TelegramLogin, FakeClient, Vault]:
    client = client or FakeClient()
    vault = Vault(tmp_path / "vault.json", backoff=False)
    if mode is not None:
        vault.create(mode, PASSWORD if mode == MODE_PASSWORD else None)
        if keys:
            vault.set("api_id", "1")
            vault.set("api_hash", "a" * 32)

    def factory(session: Any, api_id: int, api_hash: str, **_kw: Any) -> FakeClient:
        client.sessions_seen.append(session)
        return client

    login = TelegramLogin(vault=vault, client_factory=factory, idle_seconds=60, **kwargs)
    return login, client, vault


def code_of(call) -> str:  # noqa: ANN001
    with pytest.raises(ChatstyleError) as info:
        call()
    return getattr(info.value, "code", "")


# --- состояние без сети ---


def test_status_without_a_vault_is_offline(tmp_path: Path) -> None:
    login, client, _ = make_login(tmp_path, mode=None)
    state = login.status()
    assert (state.step, state.name, state.mode, state.has_keys) == (
        STEP_LOGGED_OUT,
        None,
        None,
        False,
    )
    assert client.calls == [] and client.sessions_seen == []


def test_status_reports_keys_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "5")
    monkeypatch.setenv("TELEGRAM_API_HASH", "c" * 32)
    login, _, _ = make_login(tmp_path, mode=None)
    assert login.status().has_keys is True


# --- настройка хранилища ---


def test_setup_creates_the_vault_with_keys(tmp_path: Path) -> None:
    login, _, vault = make_login(tmp_path, mode=None)
    state = login.setup(MODE_PASSWORD, PASSWORD, "123", HASH)
    assert state.mode == MODE_PASSWORD and state.has_keys and state.step == STEP_LOGGED_OUT
    raw = vault.path.read_text(encoding="utf-8")
    assert HASH not in raw and "api_hash" not in raw and PASSWORD not in raw
    vault.lock()
    vault.unlock(PASSWORD)
    assert (vault.get("api_id"), vault.get("api_hash")) == ("123", HASH)


def test_setup_in_memory_mode_writes_nothing(tmp_path: Path) -> None:
    login, _, vault = make_login(tmp_path, mode=None)
    login.setup(MODE_MEMORY, None, "123", HASH)
    assert (
        vault.mode() == MODE_MEMORY and not vault.path.exists() and list(tmp_path.iterdir()) == []
    )


@pytest.mark.parametrize(
    ("api_id", "api_hash"),
    [("abc", HASH), ("0", HASH), ("-5", HASH), ("123", "short"), ("123", "z" * 32), ("", "")],
)
def test_setup_refuses_bad_keys_and_leaves_no_vault(
    tmp_path: Path, api_id: str, api_hash: str
) -> None:
    login, _, vault = make_login(tmp_path, mode=None)
    assert code_of(lambda: login.setup(MODE_PASSWORD, PASSWORD, api_id, api_hash)) == "keys_invalid"
    assert not vault.path.exists() and vault.mode() is None


def test_setup_refuses_weak_password_unknown_mode_and_second_setup(tmp_path: Path) -> None:
    login, _, vault = make_login(tmp_path, mode=None)
    assert code_of(lambda: login.setup(MODE_PASSWORD, "short", "1", HASH)) == "password_weak"
    assert code_of(lambda: login.setup("plain", None, "1", HASH)) == "vault_bad_mode"
    assert not vault.path.exists()
    login.setup(MODE_MEMORY, None, "1", HASH)
    assert code_of(lambda: login.setup(MODE_MEMORY, None, "2", HASH)) == "vault_exists"


def test_setup_may_skip_keys_when_the_environment_has_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "5")
    monkeypatch.setenv("TELEGRAM_API_HASH", "c" * 32)
    login, _, vault = make_login(tmp_path, mode=None)
    state = login.setup(MODE_MEMORY, None, "", "")
    assert state.has_keys and vault.keys() == []


def test_save_keys_replaces_keys_only_in_an_open_vault(tmp_path: Path) -> None:
    login, _, vault = make_login(tmp_path, mode=MODE_PASSWORD)
    login.save_keys("77", HASH)
    assert (vault.get("api_id"), vault.get("api_hash")) == ("77", HASH)
    assert code_of(lambda: login.save_keys("x", HASH)) == "keys_invalid"
    login.lock()
    assert code_of(lambda: login.save_keys("78", HASH)) == "vault_locked"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI есть только в Windows")
def test_dpapi_vault_opens_itself_and_status_works(tmp_path: Path) -> None:
    login, _, _ = make_login(tmp_path, mode=None)
    login.setup(MODE_DPAPI, None, "1", HASH)
    fresh = TelegramLogin(vault=Vault(tmp_path / "vault.json"), client_factory=lambda *a, **k: None)
    state = fresh.status()
    assert state.mode == MODE_DPAPI and state.step == STEP_LOGGED_OUT and state.has_keys


# --- замок ---


def test_locked_vault_hides_everything_until_the_password(tmp_path: Path) -> None:
    login, _, vault = make_login(tmp_path, mode=MODE_PASSWORD)
    login.lock()
    state = login.status()
    assert (state.step, state.mode, state.has_keys) == (STEP_LOCKED, MODE_PASSWORD, False)
    assert code_of(lambda: login.unlock("wrong password!!")) == "wrong_password"
    assert login.status().step == STEP_LOCKED
    assert login.unlock(PASSWORD).step == STEP_LOGGED_OUT
    assert vault.unlocked()


def test_begin_needs_an_open_vault(tmp_path: Path) -> None:
    login, client, _ = make_login(tmp_path, mode=None)
    assert code_of(lambda: login.begin(PHONE)) == "vault_required"
    login2, client2, _ = make_login(tmp_path / "x", mode=MODE_PASSWORD)
    login2.lock()
    assert code_of(lambda: login2.begin(PHONE)) == "vault_locked"
    assert client.calls == [] and client2.calls == []


def test_the_vault_locks_itself_after_idle_time(tmp_path: Path) -> None:
    login, _, _ = make_login(tmp_path, mode=MODE_PASSWORD, lock_seconds=0.2)
    login.unlock(PASSWORD)
    deadline = time.time() + 5
    while login.status().step != STEP_LOCKED and time.time() < deadline:
        time.sleep(0.05)
    assert login.status().step == STEP_LOCKED


def test_memory_mode_is_not_auto_locked(tmp_path: Path) -> None:
    login, _, vault = make_login(tmp_path, mode=MODE_MEMORY, lock_seconds=0.1)
    login.save_keys("5", HASH)
    time.sleep(0.4)
    assert vault.unlocked()


# --- шаги входа ---


def test_full_login_without_2fa_stores_the_session_in_the_vault(tmp_path: Path) -> None:
    login, client, vault = make_login(
        tmp_path, FakeClient(sign_in_script=["ok"]), mode=MODE_PASSWORD
    )
    state = login.begin(PHONE)
    assert state.step == STEP_NEED_CODE and client.phone == PHONE
    assert login.status().step == STEP_NEED_CODE
    done = login.submit_code("12 345")
    assert (done.step, done.name) == (STEP_LOGGED_IN, "Иван Петров")
    assert client.sign_in_calls[0] == {
        "phone": PHONE,
        "code": "12345",
        "phone_code_hash": "HASH",
        "password": None,
    }
    assert client.disconnected
    assert (vault.get("session"), vault.get("account")) == (SAVED, "Иван Петров")
    raw = vault.path.read_text(encoding="utf-8")
    assert SAVED not in raw and "Иван" not in raw  # на диске только шифртекст
    assert login.status().step == STEP_LOGGED_IN and login.status().name == "Иван Петров"
    assert not list(paths.data_dir().glob("*.session*")) and not account_file().exists()


def test_login_with_2fa(tmp_path: Path) -> None:
    client = FakeClient(sign_in_script=[errors.SessionPasswordNeededError(request=None), "ok"])
    login, client, vault = make_login(tmp_path, client)
    login.begin(PHONE)
    assert login.submit_code("12345").step == STEP_NEED_PASSWORD
    assert login.status().step == STEP_NEED_PASSWORD
    assert login.submit_password("secret").step == STEP_LOGGED_IN
    assert client.sign_in_calls[-1]["password"] == "secret"
    assert vault.get("session") == SAVED


def test_wrong_code_can_be_retried(tmp_path: Path) -> None:
    client = FakeClient(sign_in_script=[errors.PhoneCodeInvalidError(request=None), "ok"])
    login, _, _ = make_login(tmp_path, client)
    login.begin(PHONE)
    assert code_of(lambda: login.submit_code("999")) == "code_invalid"
    assert login.status().step == STEP_NEED_CODE
    assert login.submit_code("123").step == STEP_LOGGED_IN


def test_code_without_digits_is_refused_without_calling_telegram(tmp_path: Path) -> None:
    login, client, _ = make_login(tmp_path)
    login.begin(PHONE)
    assert code_of(lambda: login.submit_code("abc")) == "code_invalid"
    assert client.sign_in_calls == []


def test_expired_code_resets_the_login_and_keeps_the_vault(tmp_path: Path) -> None:
    client = FakeClient(sign_in_script=[errors.PhoneCodeExpiredError(request=None)])
    login, _, vault = make_login(tmp_path, client)
    login.begin(PHONE)
    assert code_of(lambda: login.submit_code("123")) == "code_expired"
    assert (
        login.status().step == STEP_LOGGED_OUT and vault.unlocked() and vault.get("api_id") == "1"
    )
    assert code_of(lambda: login.submit_code("123")) == "login_not_started"


def test_wrong_2fa_password_can_be_retried(tmp_path: Path) -> None:
    client = FakeClient(
        sign_in_script=[
            errors.SessionPasswordNeededError(request=None),
            errors.PasswordHashInvalidError(request=None),
            "ok",
        ]
    )
    login, _, _ = make_login(tmp_path, client)
    login.begin(PHONE)
    login.submit_code("123")
    assert code_of(lambda: login.submit_password("bad")) == "password_invalid"
    assert login.status().step == STEP_NEED_PASSWORD
    assert login.submit_password("good").step == STEP_LOGGED_IN


@pytest.mark.parametrize(
    ("error", "expected", "params"),
    [
        (errors.PhoneNumberInvalidError(request=None), "phone_invalid", {}),
        (errors.ApiIdInvalidError(request=None), "api_invalid", {}),
        (errors.FloodWaitError(request=None, capture=90), "flood_wait", {"minutes": "2"}),
        (ConnectionError("x"), "network", {}),
        (
            errors.RPCError(request=None, message="BOOM", code=500),
            "telegram",
            {"reason": "RPCError"},
        ),
    ],
)
def test_begin_errors_become_codes_and_leave_the_vault_alone(
    tmp_path: Path, error: Exception, expected: str, params: dict
) -> None:
    client = FakeClient(send_code_error=error)
    login, _, vault = make_login(tmp_path, client)
    with pytest.raises(TelegramLoginError) as info:
        login.begin(PHONE)
    assert info.value.code == expected and info.value.params == params
    assert login.status().step == STEP_LOGGED_OUT and client.disconnected
    assert vault.get("api_id") == "1" and vault.get("session") is None


def test_connect_error_is_a_network_code(tmp_path: Path) -> None:
    login, _, _ = make_login(tmp_path, FakeClient(connect_error=ConnectionError("x")))
    assert code_of(lambda: login.begin(PHONE)) == "network"


def test_begin_without_phone_or_keys(tmp_path: Path) -> None:
    login, client, _ = make_login(tmp_path)
    assert code_of(lambda: login.begin("  ")) == "phone_invalid"
    login2, client2, _ = make_login(tmp_path / "b", keys=False)
    assert code_of(lambda: login2.begin(PHONE)) == "keys_missing"
    assert client.calls == [] and client2.calls == []


def test_begin_when_the_saved_session_is_still_valid(tmp_path: Path) -> None:
    login, client, vault = make_login(tmp_path, FakeClient(authorized=True))
    state = login.begin(PHONE)
    assert state.step == STEP_LOGGED_IN and "send_code_request" not in client.calls
    assert vault.get("account") == "Иван Петров"


def test_the_saved_session_string_is_handed_to_the_client(tmp_path: Path) -> None:
    from telethon.crypto import AuthKey
    from telethon.sessions import StringSession

    session = StringSession()
    session.set_dc(2, "149.154.167.51", 443)
    session.auth_key = AuthKey(b"\x02" * 256)
    login, client, vault = make_login(tmp_path, FakeClient(authorized=True))
    vault.set("session", session.save())
    login.begin(PHONE)
    assert client.sessions_seen[0].auth_key.key == b"\x02" * 256


def test_a_failed_new_login_keeps_the_old_session(tmp_path: Path) -> None:
    login, _, vault = make_login(tmp_path, FakeClient(connect_error=ConnectionError("x")))
    vault.set("session", "OLD-SESSION")
    vault.set("account", "Старый")
    code_of(lambda: login.begin(PHONE))
    assert (vault.get("session"), vault.get("account")) == ("OLD-SESSION", "Старый")


def test_cancel_closes_the_client(tmp_path: Path) -> None:
    login, client, vault = make_login(tmp_path)
    login.begin(PHONE)
    state = login.cancel()
    assert state.step == STEP_LOGGED_OUT and client.disconnected and vault.get("session") is None


def test_idle_login_is_cancelled(tmp_path: Path) -> None:
    login, client, _ = make_login(tmp_path)
    login._idle_seconds = 0.2
    login.begin(PHONE)
    deadline = time.time() + 5
    while login.status().step == STEP_NEED_CODE and time.time() < deadline:
        time.sleep(0.05)
    assert login.status().step == STEP_LOGGED_OUT and client.disconnected


def test_second_begin_resets_the_first(tmp_path: Path) -> None:
    first, second = FakeClient(), FakeClient()
    clients = iter([first, second])
    vault = Vault(tmp_path / "vault.json", backoff=False)
    vault.create(MODE_MEMORY)
    vault.set("api_id", "1")
    vault.set("api_hash", "a" * 32)
    login = TelegramLogin(
        vault=vault, client_factory=lambda *a, **k: next(clients), idle_seconds=60
    )
    login.begin(PHONE)
    login.begin("+79009999999")
    assert first.disconnected and not second.disconnected and second.phone == "+79009999999"


# --- выход и удаление ---


def _logged_in(tmp_path: Path, **kwargs: Any) -> tuple[TelegramLogin, FakeClient, Vault]:
    client = FakeClient(authorized=True)
    login, client, vault = make_login(tmp_path, client, **kwargs)
    login.begin(PHONE)
    return login, client, vault


def test_logout_ends_the_remote_session_and_clears_the_vault_session(tmp_path: Path) -> None:
    login, client, vault = _logged_in(tmp_path)
    state = login.logout()
    assert state.step == STEP_LOGGED_OUT and state.remote_failed is False and client.logged_out
    assert vault.get("session") is None and vault.get("account") is None
    assert vault.get("api_id") == "1"  # ключи остаются


def test_logout_removes_local_data_even_when_telegram_is_unreachable(tmp_path: Path) -> None:
    login, client, vault = _logged_in(tmp_path)
    client.connect_error = ConnectionError("нет сети")
    state = login.logout()
    assert state.step == STEP_LOGGED_OUT and state.remote_failed is True
    assert vault.get("session") is None and vault.get("account") is None


def test_logout_needs_an_open_vault(tmp_path: Path) -> None:
    login, _, _ = make_login(tmp_path, mode=MODE_PASSWORD)
    login.lock()
    assert code_of(login.logout) == "vault_locked"


def test_forget_destroys_the_vault_and_legacy_files(tmp_path: Path) -> None:
    login, client, vault = _logged_in(tmp_path, mode=MODE_PASSWORD)
    legacy = paths.session_file()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("old", encoding="utf-8")
    account_file().write_text("Старый", encoding="utf-8")
    state = login.forget()
    assert (state.step, state.mode, state.legacy) == (STEP_LOGGED_OUT, None, False)
    assert client.logged_out and not vault.path.exists() and not legacy.exists()
    assert not account_file().exists()


# --- файлы прежней версии ---


def test_legacy_plaintext_files_are_reported_and_can_be_removed(tmp_path: Path) -> None:
    login, _, _ = make_login(tmp_path, mode=None)
    legacy = paths.session_file()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("x", encoding="utf-8")
    legacy.with_name(legacy.name + "-journal").write_text("j", encoding="utf-8")
    account_file().write_text("Иван", encoding="utf-8")
    assert login.status().legacy is True
    assert login.remove_legacy_files().legacy is False
    assert not legacy.exists() and not account_file().exists()


def test_a_new_login_removes_legacy_files(tmp_path: Path) -> None:
    login, _, _ = make_login(tmp_path, FakeClient(sign_in_script=["ok"]))
    legacy = paths.session_file()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("x", encoding="utf-8")
    login.begin(PHONE)
    login.submit_code("123")
    assert not legacy.exists()


# --- секреты не утекают ---


def test_secrets_never_appear_in_errors_or_states(tmp_path: Path) -> None:
    client = FakeClient(
        sign_in_script=[
            errors.SessionPasswordNeededError(request=None),
            errors.PasswordHashInvalidError(request=None),
        ]
    )
    login, _, _ = make_login(tmp_path, client, mode=MODE_PASSWORD)
    texts: list[str] = []
    login.begin(PHONE)
    for call in (
        lambda: login.submit_code("12345"),
        lambda: login.submit_password("very-secret-pw"),
    ):
        try:
            texts.append(repr(call()))
        except TelegramLoginError as exc:
            texts.append(f"{exc} {exc.params} {exc.code}")
    texts.append(repr(login.status()))
    try:
        login.unlock("wrong password!!")
    except VaultError as exc:
        texts.append(f"{exc} {exc.params}")
    joined = " ".join(texts)
    for secret in (
        "12345",
        "very-secret-pw",
        "a" * 32,
        PASSWORD,
        "wrong password",
        SAVED,
    ):
        assert secret not in joined, secret
    assert json.dumps(texts)  # всё сериализуется как обычный текст


# --- двухфакторная защита аккаунта ---


@pytest.mark.parametrize(
    ("has_password", "expected"), [(True, True), (False, False), (RuntimeError("нет"), None)]
)
def test_two_factor_state_is_checked_after_login_and_remembered(
    tmp_path: Path, has_password: bool | Exception, expected: bool | None
) -> None:
    client = FakeClient(authorized=True)
    client.has_password = has_password
    login, _, vault = make_login(tmp_path, client)
    assert login.begin(PHONE).two_factor is expected
    assert login.status().two_factor is expected
    assert login.logout().two_factor is None
    assert vault.get("two_factor") is None
