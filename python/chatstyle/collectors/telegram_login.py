"""Вход в Telegram по шагам для окна: телефон, код, пароль 2FA, выход, сохранение ключей.

Те же сессия и файл `.env`, что у `chatstyle login`, поэтому вход из окна и из терминала
взаимозаменяемы. Код из Telegram и пароль нигде не сохраняются и не попадают в сообщения об
ошибках; из секретов на диск уходят только ключи `api_id`/`api_hash` (в `.env`, по просьбе
пользователя) и сама сессия Telethon. Сеть используется только при явных вызовах `begin`,
`submit_code`, `submit_password` и `logout`; `status` работает без сети.

Клиент Telethon живёт в отдельном потоке со своим циклом событий между шагами входа и закрывается
при завершении, отмене или бездействии (`IDLE_SECONDS`).
"""

import asyncio
import os
import re
import sys
import threading
from collections.abc import Callable
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chatstyle.collectors.telegram import ClientFactory, _telethon_client_factory
from chatstyle.config import (
    API_HASH_VAR,
    API_ID_VAR,
    TelegramCredentials,
    load_telegram_credentials,
)
from chatstyle.errors import ChatstyleError, CodedError
from chatstyle.paths import data_dir, env_file, session_file

IDLE_SECONDS = 300.0
CALL_TIMEOUT = 60.0
API_HASH_PATTERN = re.compile(r"[0-9a-fA-F]{32}")
ACCOUNT_FILE_NAME = "telegram.account"

STEP_LOGGED_OUT = "logged_out"
STEP_NEED_CODE = "need_code"
STEP_NEED_PASSWORD = "need_password"
STEP_LOGGED_IN = "logged_in"


class TelegramLoginError(CodedError):
    """Ошибка шага входа: код для перевода в окне и параметры (строки, без секретов)."""


@dataclass(frozen=True)
class LoginState:
    """Где находится вход: шаг, имя аккаунта и ключи ли заданы."""

    step: str
    name: str | None = None
    has_keys: bool = True
    remote_failed: bool = False


def account_file() -> Path:
    """Файл с именем аккаунта: по нему окно без сети показывает, что вход выполнен."""
    return data_dir() / ACCOUNT_FILE_NAME


def _restrict_permissions(path: Path) -> None:
    """Файл с секретами только для владельца (на POSIX; в Windows права задаёт каталог)."""
    if sys.platform != "win32":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _delete(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _session_files(session: Path) -> list[Path]:
    """Файл сессии Telethon и его sqlite-журнал."""
    base = session if session.suffix else session.with_suffix(".session")
    return [base, base.with_name(base.name + "-journal")]


class _LoopThread:
    """Поток с циклом событий: клиент Telethon создаётся и живёт внутри него."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coroutine: Any, timeout: float = CALL_TIMEOUT) -> Any:
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise TimeoutError("Telegram не ответил вовремя.") from exc

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        if not self._loop.is_running():
            self._loop.close()


def _translate(exc: Exception) -> TelegramLoginError | None:
    """Ошибка Telethon или сети -> ошибка шага входа; None — не наша ошибка."""
    from telethon import errors

    if isinstance(exc, errors.FloodWaitError):
        minutes = max(1, -(-int(exc.seconds) // 60))
        return TelegramLoginError(
            "flood_wait", f"Telegram просит подождать около {minutes} мин.", minutes=minutes
        )
    if isinstance(exc, errors.ApiIdInvalidError):
        return TelegramLoginError("api_invalid", "Telegram отклонил ключи api_id и api_hash.")
    if isinstance(exc, errors.PhoneNumberInvalidError):
        return TelegramLoginError("phone_invalid", "Номер телефона не принят Telegram.")
    if isinstance(exc, errors.PhoneCodeInvalidError | errors.PhoneCodeEmptyError):
        return TelegramLoginError("code_invalid", "Неверный код.")
    if isinstance(exc, errors.PhoneCodeExpiredError):
        return TelegramLoginError("code_expired", "Код устарел.")
    if isinstance(exc, errors.PasswordHashInvalidError):
        return TelegramLoginError("password_invalid", "Неверный пароль.")
    if isinstance(exc, errors.RPCError):
        return TelegramLoginError(
            "telegram", f"Ошибка Telegram: {type(exc).__name__}", reason=type(exc).__name__
        )
    if isinstance(exc, ConnectionError | TimeoutError | OSError):
        return TelegramLoginError("network", "Нет соединения с Telegram.")
    return None


def _full_name(me: Any) -> str:
    parts = [getattr(me, "first_name", None), getattr(me, "last_name", None)]
    name = " ".join(part for part in parts if part)
    return name or getattr(me, "username", None) or str(getattr(me, "id", ""))


class TelegramLogin:
    """Пошаговый вход. Методы синхронные, их вызывают из потока окна; доступ под замком."""

    def __init__(
        self,
        credentials_loader: Callable[[], TelegramCredentials] = load_telegram_credentials,
        session: Path | None = None,
        client_factory: ClientFactory | None = None,
        idle_seconds: float = IDLE_SECONDS,
    ) -> None:
        self._load_credentials = credentials_loader
        self._session = session
        self._factory = client_factory or _telethon_client_factory
        self._idle_seconds = idle_seconds
        self._lock = threading.RLock()
        self._loop: _LoopThread | None = None
        self._client: Any = None
        self._phone = ""
        self._phone_code_hash = ""
        self._had_session = False  # сессия была до входа: при отмене её нельзя удалять
        self._timer: threading.Timer | None = None

    # --- состояние без сети ---

    def session_path(self) -> Path:
        return self._session if self._session is not None else session_file()

    def has_keys(self) -> bool:
        try:
            self._load_credentials()
        except ChatstyleError:
            return False
        return True

    def status(self) -> LoginState:
        """Без обращения к сети: по сохранённым ключам, сессии и имени аккаунта."""
        with self._lock:
            has_keys = self.has_keys()
            if self._client is not None:
                step = STEP_NEED_PASSWORD if self._phone_code_hash == "" else STEP_NEED_CODE
                return LoginState(step, has_keys=has_keys)
            if _session_files(self.session_path())[0].exists() and account_file().exists():
                try:
                    name = account_file().read_text(encoding="utf-8").strip()
                except (OSError, UnicodeDecodeError):
                    name = ""
                return LoginState(STEP_LOGGED_IN, name or None, has_keys)
            return LoginState(STEP_LOGGED_OUT, None, has_keys)

    # --- ключи ---

    def save_keys(self, api_id: str, api_hash: str) -> None:
        """Записать ключи в .env каталога данных, сохранив остальные строки файла."""
        api_id = api_id.strip()
        api_hash = api_hash.strip()
        if not api_id.isdecimal() or int(api_id) <= 0:
            raise TelegramLoginError("keys_invalid", "api_id должен быть числом.")
        if not API_HASH_PATTERN.fullmatch(api_hash):
            raise TelegramLoginError("keys_invalid", "api_hash — 32 символа 0-9 и a-f.")
        path = env_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeDecodeError):
            lines = []
        kept = [
            line
            for line in lines
            if line.strip().removeprefix("export ").partition("=")[0].strip()
            not in (API_ID_VAR, API_HASH_VAR)
        ]
        kept += [f"{API_ID_VAR}={api_id}", f"{API_HASH_VAR}={api_hash}"]
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text("\n".join(kept) + "\n", encoding="utf-8")
        _restrict_permissions(temporary)
        os.replace(temporary, path)

    # --- шаги входа ---

    def begin(self, phone: str) -> LoginState:
        """Запросить код: Telegram пришлёт его в приложение. Возвращает need_code или logged_in."""
        phone = phone.strip()
        if not phone:
            raise TelegramLoginError("phone_invalid", "Укажите номер телефона.")
        with self._lock:
            self._reset()
            try:
                credentials = self._load_credentials()
            except ChatstyleError as exc:
                raise TelegramLoginError("keys_missing", "Не заданы ключи Telegram API.") from exc
            self._had_session = _session_files(self.session_path())[0].exists()
            self._loop = _LoopThread()
            try:
                state = self._loop.run(self._begin(credentials, phone))
            except BaseException as exc:
                self._reset()
                raise self._error(exc) from exc
            self._arm_timer()
            return state

    def submit_code(self, code: str) -> LoginState:
        """Отправить код из Telegram: need_password, если включена двухфакторная защита."""
        with self._lock:
            self._require_started()
            digits = "".join(ch for ch in code if ch.isdigit())
            if not digits:
                raise TelegramLoginError("code_invalid", "Введите код из Telegram.")
            try:
                state = self._loop.run(self._submit_code(digits))  # type: ignore[union-attr]
            except BaseException as exc:
                translated = self._error(exc)
                if translated.code in {"code_expired", "network", "flood_wait", "telegram"}:
                    self._reset()
                raise translated from exc
            self._arm_timer()
            return state

    def submit_password(self, password: str) -> LoginState:
        """Отправить пароль двухфакторной защиты."""
        with self._lock:
            self._require_started()
            if not password:
                raise TelegramLoginError("password_invalid", "Введите пароль.")
            try:
                return self._loop.run(self._submit_password(password))  # type: ignore[union-attr]
            except BaseException as exc:
                translated = self._error(exc)
                if translated.code in {"network", "flood_wait", "telegram"}:
                    self._reset()
                raise translated from exc

    def cancel(self) -> LoginState:
        """Прервать вход: клиент закрывается, незаконченная сессия удаляется."""
        with self._lock:
            self._reset()
            return self.status()

    def logout(self) -> LoginState:
        """Выйти: завершить сессию в Telegram (если удалось) и удалить локальные файлы."""
        with self._lock:
            self._reset()
            remote_failed = False
            if _session_files(self.session_path())[0].exists():
                try:
                    credentials = self._load_credentials()
                    loop = _LoopThread()
                    try:
                        loop.run(self._log_out(credentials))
                    finally:
                        loop.stop()
                except Exception:  # noqa: BLE001 - локальный выход выполняется при любом отказе сети
                    remote_failed = True
            for path in _session_files(self.session_path()):
                _delete(path)
            _delete(account_file())
            return LoginState(STEP_LOGGED_OUT, None, self.has_keys(), remote_failed)

    # --- внутренности ---

    def _error(self, exc: BaseException) -> TelegramLoginError:
        if isinstance(exc, TelegramLoginError):
            return exc
        if isinstance(exc, Exception):
            translated = _translate(exc)
            if translated is not None:
                return translated
        raise exc

    def _require_started(self) -> None:
        if self._client is None or self._loop is None:
            raise TelegramLoginError("login_not_started", "Сначала запросите код.")

    def _new_client(self, credentials: TelegramCredentials) -> Any:
        session = self.session_path()
        session.parent.mkdir(parents=True, exist_ok=True)
        return self._factory(str(session), credentials.api_id, credentials.api_hash)

    async def _begin(self, credentials: TelegramCredentials, phone: str) -> LoginState:
        client = self._new_client(credentials)
        self._client = client
        await client.connect()
        if await client.is_user_authorized():
            return await self._finish()
        sent = await client.send_code_request(phone)
        self._phone = phone
        self._phone_code_hash = sent.phone_code_hash
        return LoginState(STEP_NEED_CODE)

    async def _submit_code(self, code: str) -> LoginState:
        from telethon import errors

        try:
            await self._client.sign_in(
                phone=self._phone, code=code, phone_code_hash=self._phone_code_hash
            )
        except errors.SessionPasswordNeededError:
            self._phone_code_hash = ""
            return LoginState(STEP_NEED_PASSWORD)
        return await self._finish()

    async def _submit_password(self, password: str) -> LoginState:
        await self._client.sign_in(password=password)
        return await self._finish()

    async def _finish(self) -> LoginState:
        me = await self._client.get_me()
        name = _full_name(me)
        await self._client.disconnect()
        self._client = None
        session = self.session_path()
        _restrict_permissions(_session_files(session)[0])
        account = account_file()
        account.parent.mkdir(parents=True, exist_ok=True)
        account.write_text(name, encoding="utf-8")
        _restrict_permissions(account)
        self._stop_loop_later()
        return LoginState(STEP_LOGGED_IN, name)

    async def _log_out(self, credentials: TelegramCredentials) -> None:
        client = self._new_client(credentials)
        await client.connect()
        try:
            if await client.is_user_authorized():
                await client.log_out()
        finally:
            await client.disconnect()

    def _stop_loop_later(self) -> None:
        """Цикл останавливается вне собственного потока, после завершения шага."""
        loop = self._loop
        self._loop = None
        if loop is not None:
            threading.Thread(target=loop.stop, daemon=True).start()
        self._cancel_timer()

    def _arm_timer(self) -> None:
        self._cancel_timer()
        if self._client is not None:
            self._timer = threading.Timer(self._idle_seconds, self.cancel)
            self._timer.daemon = True
            self._timer.start()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _reset(self) -> None:
        """Закрыть клиент и цикл; недоведённый до конца вход не оставляет файлов сессии."""
        self._cancel_timer()
        unfinished = self._client is not None
        loop, client = self._loop, self._client
        self._loop = None
        self._client = None
        self._phone = ""
        self._phone_code_hash = ""
        if loop is not None:
            if client is not None:
                try:
                    loop.run(client.disconnect(), timeout=10)
                except Exception:  # noqa: BLE001, S110 - закрытие не должно мешать отмене
                    pass
            loop.stop()
        if unfinished and not self._had_session:
            for path in _session_files(self.session_path()):
                _delete(path)
