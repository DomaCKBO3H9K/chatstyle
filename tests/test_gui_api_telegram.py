"""Методы Api для входа в Telegram и параметры сбора tg: (без сети, вход подменён заглушкой)."""

import time
import webbrowser
from pathlib import Path

import pytest
from chatstyle.collectors.telegram_login import (
    STEP_LOGGED_IN,
    STEP_LOGGED_OUT,
    STEP_NEED_CODE,
    LoginState,
    TelegramLoginError,
)
from chatstyle.errors import ChatstyleError, CodedError
from chatstyle.gui import api as gui_api
from chatstyle.gui.model import BackgroundJob, CompareForm, check_compare_form


class FakeLogin:
    """Подмена TelegramLogin: записывает вызовы и отвечает по сценарию."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.next_error: Exception | None = None
        self.state = LoginState(STEP_LOGGED_OUT, None, True)

    def _answer(self, name: str, *args: object, state: LoginState | None = None) -> LoginState:
        self.calls.append((name, *args))
        if self.next_error is not None:
            error, self.next_error = self.next_error, None
            raise error
        if state is not None:
            self.state = state
        return self.state

    def touch(self) -> None:
        self.calls.append(("touch",))

    def status(self) -> LoginState:
        return self.state

    def setup(self, mode: str, password: str | None, api_id: str, api_hash: str) -> LoginState:
        return self._answer(
            "setup", mode, password, api_id, api_hash, state=LoginState(STEP_LOGGED_OUT, mode=mode)
        )

    def unlock(self, password: str | None) -> LoginState:
        return self._answer("unlock", password, state=LoginState(STEP_LOGGED_OUT, mode="password"))

    def lock(self) -> LoginState:
        return self._answer("lock", state=LoginState("locked", mode="password"))

    def forget(self) -> LoginState:
        return self._answer("forget", state=LoginState(STEP_LOGGED_OUT))

    def remove_legacy_files(self) -> LoginState:
        return self._answer("remove_legacy", state=LoginState(STEP_LOGGED_OUT))

    def shutdown(self) -> None:
        self.calls.append(("shutdown",))

    def save_keys(self, api_id: str, api_hash: str) -> None:
        self._answer("save_keys", api_id, api_hash)

    def begin(self, phone: str) -> LoginState:
        return self._answer("begin", phone, state=LoginState(STEP_NEED_CODE))

    def submit_code(self, code: str) -> LoginState:
        return self._answer("code", code, state=LoginState(STEP_LOGGED_IN, "Иван Петров"))

    def submit_password(self, password: str) -> LoginState:
        return self._answer("password", password, state=LoginState(STEP_LOGGED_IN, "Иван"))

    def cancel(self) -> LoginState:
        return self._answer("cancel", state=LoginState(STEP_LOGGED_OUT))

    def logout(self) -> LoginState:
        return self._answer("logout", state=LoginState(STEP_LOGGED_OUT, remote_failed=True))


@pytest.fixture
def api_and_login() -> tuple[gui_api.Api, FakeLogin]:
    login = FakeLogin()
    return gui_api.Api(telegram=login), login  # type: ignore[arg-type]


def test_status_is_a_plain_dictionary(api_and_login: tuple[gui_api.Api, FakeLogin]) -> None:
    api, login = api_and_login
    assert api.telegram_status() == {
        "step": "logged_out",
        "name": None,
        "has_keys": True,
        "remote_failed": False,
        "mode": None,
        "legacy": False,
        "problem": None,
        "two_factor": None,
    }
    assert login.calls == []  # статус не ходит в сеть


def test_login_steps_return_state_and_pass_arguments(
    api_and_login: tuple[gui_api.Api, FakeLogin],
) -> None:
    api, login = api_and_login
    assert api.telegram_begin("+7 900")["state"]["step"] == "need_code"
    done = api.telegram_code("12345")
    assert done == {
        "ok": True,
        "state": {
            "step": "logged_in",
            "name": "Иван Петров",
            "has_keys": True,
            "remote_failed": False,
            "mode": None,
            "legacy": False,
            "problem": None,
            "two_factor": None,
        },
    }
    assert api.telegram_password("pw")["ok"] is True
    steps = [call for call in login.calls if call != ("touch",)]
    assert steps == [("begin", "+7 900"), ("code", "12345"), ("password", "pw")]


def test_save_keys_returns_the_new_status(api_and_login: tuple[gui_api.Api, FakeLogin]) -> None:
    api, login = api_and_login
    answer = api.telegram_save_keys("123", "a" * 32)
    assert answer["ok"] is True and answer["state"]["has_keys"] is True
    assert [c for c in login.calls if c != ("touch",)] == [("save_keys", "123", "a" * 32)]


def test_logout_reports_when_the_remote_session_could_not_be_ended(
    api_and_login: tuple[gui_api.Api, FakeLogin],
) -> None:
    api, _ = api_and_login
    answer = api.telegram_logout()
    assert answer["state"]["step"] == "logged_out" and answer["state"]["remote_failed"] is True
    assert api.telegram_cancel()["ok"] is True


def test_coded_errors_become_codes_with_string_params(
    api_and_login: tuple[gui_api.Api, FakeLogin],
) -> None:
    api, login = api_and_login
    login.next_error = TelegramLoginError("flood_wait", "жди", minutes=3)
    assert api.telegram_begin("+7") == {
        "ok": False,
        "error": {"code": "flood_wait", "params": {"minutes": "3"}},
    }
    login.next_error = TelegramLoginError("code_invalid", "Неверный код.")
    assert api.telegram_code("1")["error"] == {"code": "code_invalid", "params": {}}


def test_plain_chatstyle_errors_become_core_errors(
    api_and_login: tuple[gui_api.Api, FakeLogin],
) -> None:
    api, login = api_and_login
    login.next_error = ChatstyleError("Что-то на русском")
    answer = api.telegram_begin("+7")
    assert answer["error"] == {"code": "core", "params": {"message": "Что-то на русском"}}


def test_secrets_are_not_part_of_any_answer(api_and_login: tuple[gui_api.Api, FakeLogin]) -> None:
    api, login = api_and_login
    login.next_error = TelegramLoginError("password_invalid", "Неверный пароль.")
    answer = api.telegram_password("very-secret-password")
    assert "very-secret-password" not in repr(answer)
    api.telegram_save_keys("123", "b" * 32)
    assert "b" * 32 not in repr(api.telegram_status())


def test_open_site_opens_only_the_fixed_address(
    api_and_login: tuple[gui_api.Api, FakeLogin], monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
    api_and_login[0].telegram_open_site()
    assert opened == ["https://my.telegram.org"]


# --- сбор из tg:: лимит и «заново» ---


def _form(**changes: object) -> dict:
    form = {
        "unknown": "file:u.txt",
        "candidates": ["file:a.txt"],
        "impostors_dir": "",
        "seed": "1",
        "report_path": "",
    }
    return {**form, **changes}


def test_limit_and_refresh_are_validated() -> None:
    api = gui_api.Api(telegram=FakeLogin(), allowed_paths=["u.txt", "a.txt"])  # type: ignore[arg-type]
    for bad in ("abc", "0", "-5", "1.5"):
        errors = api.start_compare(_form(limit=bad))["errors"]
        assert errors == [{"code": "bad_limit", "params": {}}], bad
    assert check_compare_form(CompareForm("u", ("a",), limit=None))[0].code == "bad_limit"


def test_limit_and_refresh_reach_the_collector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[CompareForm] = []
    monkeypatch.setattr(gui_api, "run_compare", lambda form: seen.append(form) or object())
    api = gui_api.Api(telegram=FakeLogin(), allowed_paths=["u.txt", "a.txt"])  # type: ignore[arg-type]
    assert api.start_compare(_form(limit="250", refresh=True))["ok"] is True
    deadline = time.time() + 5
    while not seen and time.time() < deadline:
        time.sleep(0.02)
    assert seen[0].limit == 250 and seen[0].refresh is True


def test_collector_options_are_built_from_the_form(monkeypatch: pytest.MonkeyPatch) -> None:
    from chatstyle.gui import model

    captured: dict = {}

    def fake_run_comparison(unknown, candidates, options, **kwargs):  # noqa: ANN001, ANN202
        captured["options"] = options
        raise ChatstyleError("стоп")

    monkeypatch.setattr(model, "run_comparison", fake_run_comparison)
    form = CompareForm("file:u.txt", ("file:a.txt",), limit=250, refresh=True)
    with pytest.raises(ChatstyleError):
        model.run_compare(form)
    assert captured["options"].limit == 250 and captured["options"].refresh is True


# --- код ошибки из фоновой задачи ---


def test_coded_error_of_a_background_job_reaches_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(form):  # noqa: ANN001, ANN202
        raise CodedError("telegram_not_logged_in", "Нет входа в Telegram.")

    monkeypatch.setattr(gui_api, "run_compare", failing)
    api = gui_api.Api(telegram=FakeLogin(), allowed_paths=["u.txt", "a.txt"])  # type: ignore[arg-type]
    assert api.start_compare(_form())["ok"] is True
    state: dict = {}
    deadline = time.time() + 5
    while time.time() < deadline:
        state = api.poll()
        if state["state"] != "running":
            break
        time.sleep(0.02)
    assert state["error"] == {"code": "telegram_not_logged_in", "params": {}}
    assert api.poll() == {"state": "idle"}


def test_background_job_keeps_the_code_only_for_coded_errors() -> None:
    plain = BackgroundJob(lambda: (_ for _ in ()).throw(ChatstyleError("обычная")))
    plain.start()
    while plain.poll() is None:
        time.sleep(0.01)
    assert plain.error_code is None
    coded = BackgroundJob(lambda: (_ for _ in ()).throw(CodedError("network", "x", message="y")))
    coded.start()
    while coded.poll() is None:
        time.sleep(0.01)
    assert coded.error_code == "network" and coded.error_params == {"message": "y"}


# --- хранилище: настройка, замок, удаление ---


def test_setup_unlock_lock_forget_pass_arguments_and_return_the_mode(
    api_and_login: tuple[gui_api.Api, FakeLogin],
) -> None:
    api, login = api_and_login
    assert (
        api.telegram_setup("password", "pw-123456789", "5", "a" * 32)["state"]["mode"] == "password"
    )
    assert api.telegram_setup("memory", "", "5", "a" * 32)["ok"] is True
    assert api.telegram_unlock("pw-123456789")["ok"] is True
    assert api.telegram_lock()["state"]["step"] == "locked"
    assert api.telegram_forget()["state"]["step"] == "logged_out"
    assert api.telegram_remove_legacy()["ok"] is True
    steps = [call for call in login.calls if call != ("touch",)]
    assert steps[0] == ("setup", "password", "pw-123456789", "5", "a" * 32)
    assert steps[1] == ("setup", "memory", None, "5", "a" * 32)  # пустой пароль -> None
    assert steps[2] == ("unlock", "pw-123456789")


def test_vault_errors_are_codes(api_and_login: tuple[gui_api.Api, FakeLogin]) -> None:
    from chatstyle.securestore import VaultError

    api, login = api_and_login
    login.next_error = VaultError("wrong_password", "Неверный мастер-пароль.")
    assert api.telegram_unlock("x" * 12)["error"] == {"code": "wrong_password", "params": {}}
    login.next_error = VaultError("password_weak", "слабый", n=10)
    assert api.telegram_setup("password", "short", "5", "a" * 32)["error"] == {
        "code": "password_weak",
        "params": {"n": "10"},
    }


def test_shutdown_reaches_the_login(api_and_login: tuple[gui_api.Api, FakeLogin]) -> None:
    api, login = api_and_login
    api.shutdown()
    assert ("shutdown",) in login.calls
