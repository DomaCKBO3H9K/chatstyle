"""Вход в Telegram по шагам для окна: настройка хранилища, телефон, код, пароль 2FA, выход.

Секреты (ключи API и сессия Telethon в виде строки) лежат только в зашифрованном хранилище
``chatstyle.securestore`` (мастер-пароль, DPAPI или только память). Код из Telegram и пароль 2FA
нигде не сохраняются и не попадают в сообщения об ошибках. Сеть используется только при явных
вызовах ``begin``, ``submit_code``, ``submit_password`` и ``logout``; ``status`` работает без сети.

Клиент Telethon живёт в отдельном потоке со своим циклом событий между шагами входа и закрывается
при завершении, отмене или бездействии (``IDLE_SECONDS``). Хранилище с мастер-паролем
блокируется само после ``LOCK_SECONDS`` бездействия.
"""

import asyncio
import re
import threading
from collections.abc import Callable
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chatstyle.collectors.telegram import ClientFactory, _telethon_client_factory
from chatstyle.config import (
    VAULT_ACCOUNT,
    VAULT_API_HASH,
    VAULT_API_ID,
    VAULT_SESSION,
    TelegramCredentials,
    load_credentials_with_vault,
    load_telegram_credentials,
)
from chatstyle.errors import ChatstyleError, CodedError
from chatstyle.paths import data_dir, session_file
from chatstyle.securestore import (
    MODE_MEMORY,
    MODE_PASSWORD,
    MODES,
    Vault,
    VaultError,
    default_vault,
)

IDLE_SECONDS = 300.0
LOCK_SECONDS = 900.0
CALL_TIMEOUT = 60.0
API_HASH_PATTERN = re.compile(r"[0-9a-fA-F]{32}")
ACCOUNT_FILE_NAME = "telegram.account"

STEP_LOCKED = "locked"
STEP_LOGGED_OUT = "logged_out"
STEP_NEED_CODE = "need_code"
STEP_NEED_PASSWORD = "need_password"
STEP_LOGGED_IN = "logged_in"

KEY_API_ID, KEY_API_HASH = VAULT_API_ID, VAULT_API_HASH
KEY_SESSION, KEY_ACCOUNT = VAULT_SESSION, VAULT_ACCOUNT
KEY_TWO_FACTOR = "two_factor"  # "yes" / "no": результат проверки после входа


class TelegramLoginError(CodedError):
    """Ошибка шага входа: код для перевода в окне и параметры (строки, без секретов)."""


@dataclass(frozen=True)
class LoginState:
    """Где находится вход и в каком состоянии хранилище."""

    step: str
    name: str | None = None
    has_keys: bool = True
    remote_failed: bool = False
    mode: str | None = None  # режим хранилища: password, dpapi, memory или None, если его нет
    legacy: bool = False  # остались открытые файлы старой версии (сессия, имя аккаунта)
    problem: str | None = None  # код проблемы хранилища (например, vault_corrupt)
    two_factor: bool | None = None  # включена ли у аккаунта двухфакторная защита (None: неизвестно)


def account_file() -> Path:
    """Старый открытый файл с именем аккаунта (до появления хранилища)."""
    return data_dir() / ACCOUNT_FILE_NAME


def _legacy_files() -> list[Path]:
    """Открытые файлы прежней версии: сессия SQLite, её журнал и имя аккаунта."""
    session = session_file()
    base = session if session.suffix else session.with_suffix(".session")
    return [base, base.with_name(base.name + "-journal"), account_file()]


def _delete(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


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


async def _two_factor_enabled(client: Any) -> bool | None:
    """Есть ли у аккаунта облачный пароль (двухфакторная защита); None, если узнать не вышло."""
    try:
        from telethon.tl.functions.account import GetPasswordRequest

        return bool((await client(GetPasswordRequest())).has_password)
    except Exception:  # noqa: BLE001 - предупреждение необязательно, вход от него не зависит
        return None


def _string_session(saved: str, *, strict: bool = False) -> Any:
    """Сессия Telethon из сохранённой строки.

    Повреждённая строка при входе означает «входа нет» (начнётся новый вход), а при выходе
    (strict) — ошибку: удалённую сессию по такой строке завершить нельзя.
    """
    from telethon.sessions import StringSession

    try:
        return StringSession(saved or None)
    except ValueError:
        if strict:
            raise
        return StringSession(None)


class TelegramLogin:
    """Пошаговый вход. Методы синхронные, их вызывают из потока окна; доступ под замком."""

    def __init__(
        self,
        vault: Vault | None = None,
        credentials_loader: Callable[[], TelegramCredentials] | None = None,
        client_factory: ClientFactory | None = None,
        idle_seconds: float = IDLE_SECONDS,
        lock_seconds: float = LOCK_SECONDS,
    ) -> None:
        self._vault_override = vault
        self._credentials_loader = credentials_loader
        self._factory = client_factory or _telethon_client_factory
        self._idle_seconds = idle_seconds
        self._lock_seconds = lock_seconds
        self._lock = threading.RLock()
        self._loop: _LoopThread | None = None
        self._client: Any = None
        self._phone = ""
        self._phone_code_hash = ""
        self._timer: threading.Timer | None = None
        self._lock_timer: threading.Timer | None = None

    @property
    def vault(self) -> Vault:
        return self._vault_override if self._vault_override is not None else default_vault()

    def _credentials(self) -> TelegramCredentials:
        if self._credentials_loader is not None:
            return self._credentials_loader()
        return load_credentials_with_vault(self.vault)

    # --- состояние без сети ---

    def has_keys(self) -> bool:
        try:
            self._credentials()
        except ChatstyleError:
            return False
        return True

    def status(self) -> LoginState:
        """Без обращения к сети: режим хранилища, шаг входа, имя аккаунта, заданы ли ключи."""
        with self._lock:
            vault = self.vault
            legacy = any(path.exists() for path in _legacy_files())
            mode = vault.mode()
            problem: str | None = None
            if self._client is not None:
                step = STEP_NEED_PASSWORD if self._phone_code_hash == "" else STEP_NEED_CODE
                return LoginState(step, has_keys=self.has_keys(), mode=mode, legacy=legacy)
            if vault.exists() and not vault.unlocked():
                if vault.needs_password():
                    return LoginState(STEP_LOCKED, has_keys=False, mode=mode, legacy=legacy)
                try:
                    vault.unlock()  # DPAPI открывается без пароля
                except VaultError as exc:
                    problem = exc.code
            if vault.unlocked():
                session, account = vault.get(KEY_SESSION), vault.get(KEY_ACCOUNT)
                if session and account:
                    flag = vault.get(KEY_TWO_FACTOR)
                    return LoginState(
                        STEP_LOGGED_IN,
                        account,
                        self.has_keys(),
                        mode=mode,
                        legacy=legacy,
                        two_factor=None if flag is None else flag == "yes",
                    )
            return LoginState(
                STEP_LOGGED_OUT, None, self.has_keys(), mode=mode, legacy=legacy, problem=problem
            )

    # --- хранилище и ключи ---

    def setup(self, mode: str, password: str | None, api_id: str, api_hash: str) -> LoginState:
        """Создать хранилище выбранного режима и сохранить в нём ключи API."""
        with self._lock:
            if mode not in MODES:
                raise TelegramLoginError("vault_bad_mode", "Неизвестный режим хранения.")
            keys = self._checked_keys(api_id, api_hash, optional=self._env_keys())
            vault = self.vault
            if vault.exists() or vault.unlocked():
                raise TelegramLoginError("vault_exists", "Хранилище уже создано.")
            vault.create(mode, password)
            try:
                if keys is not None:
                    vault.set(KEY_API_ID, keys[0])
                    vault.set(KEY_API_HASH, keys[1])
            except BaseException:
                vault.destroy()
                raise
            self._arm_lock_timer()
            return self.status()

    def save_keys(self, api_id: str, api_hash: str) -> LoginState:
        """Заменить ключи API в открытом хранилище."""
        with self._lock:
            keys = self._checked_keys(api_id, api_hash, optional=False)
            if keys is None or not self.vault.unlocked():
                raise TelegramLoginError("vault_locked", "Хранилище заблокировано.")
            self.vault.set(KEY_API_ID, keys[0])
            self.vault.set(KEY_API_HASH, keys[1])
            self._arm_lock_timer()
            return self.status()

    def unlock(self, password: str | None) -> LoginState:
        """Открыть хранилище мастер-паролем (для режима DPAPI пароль не нужен)."""
        with self._lock:
            self.vault.unlock(password)
            self._arm_lock_timer()
            return self.status()

    def lock(self) -> LoginState:
        """Закрыть хранилище и прервать незаконченный вход."""
        with self._lock:
            self._reset()
            self._cancel_lock_timer()
            if self.vault.mode() != MODE_MEMORY:
                self.vault.lock()
            return self.status()

    @staticmethod
    def _env_keys() -> bool:
        try:
            load_telegram_credentials()
        except ChatstyleError:
            return False
        return True

    @staticmethod
    def _checked_keys(api_id: str, api_hash: str, *, optional: bool) -> tuple[str, str] | None:
        api_id, api_hash = api_id.strip(), api_hash.strip()
        if optional and not api_id and not api_hash:
            return None  # ключи уже заданы переменными окружения или .env
        if not api_id.isdecimal() or int(api_id) <= 0:
            raise TelegramLoginError("keys_invalid", "api_id должен быть числом.")
        if not API_HASH_PATTERN.fullmatch(api_hash):
            raise TelegramLoginError("keys_invalid", "api_hash — 32 символа 0-9 и a-f.")
        return api_id, api_hash

    # --- шаги входа ---

    def begin(self, phone: str) -> LoginState:
        """Запросить код: Telegram пришлёт его в приложение. Возвращает need_code или logged_in."""
        phone = phone.strip()
        if not phone:
            raise TelegramLoginError("phone_invalid", "Укажите номер телефона.")
        with self._lock:
            self._reset()
            vault = self.vault
            if not vault.unlocked():
                code = "vault_locked" if vault.exists() else "vault_required"
                raise TelegramLoginError(code, "Хранилище не открыто.")
            try:
                credentials = self._credentials()
            except ChatstyleError as exc:
                raise TelegramLoginError("keys_missing", "Не заданы ключи Telegram API.") from exc
            self._loop = _LoopThread()
            try:
                state = self._loop.run(self._begin(credentials, phone))
            except BaseException as exc:
                self._reset()
                raise self._error(exc) from exc
            self._arm_timer()
            self._arm_lock_timer()
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
        """Прервать вход: клиент закрывается, в хранилище ничего не меняется."""
        with self._lock:
            self._reset()
            return self.status()

    def logout(self) -> LoginState:
        """Выйти: завершить сессию в Telegram (если удалось) и стереть её из хранилища."""
        with self._lock:
            self._reset()
            vault = self.vault
            if not vault.unlocked():
                raise TelegramLoginError("vault_locked", "Хранилище заблокировано.")
            remote_failed = self._remote_logout()
            vault.set(KEY_SESSION, None)
            vault.set(KEY_ACCOUNT, None)
            vault.set(KEY_TWO_FACTOR, None)
            self._remove_legacy()
            return self._with_remote(self.status(), remote_failed)

    def forget(self) -> LoginState:
        """Удалить всё: завершить сессию в Telegram (если можно), хранилище и старые файлы."""
        with self._lock:
            self._reset()
            self._cancel_lock_timer()
            remote_failed = False
            if self.vault.unlocked() and self.vault.get(KEY_SESSION):
                remote_failed = self._remote_logout()
            self.vault.destroy()
            self._remove_legacy()
            return self._with_remote(self.status(), remote_failed)

    def touch(self) -> None:
        """Отметить активность: замок хранилища с паролем отсчитывает время заново."""
        with self._lock:
            if self.vault.unlocked():
                self._arm_lock_timer()

    def shutdown(self) -> None:
        """Закрытие окна: прервать вход; в режиме «только память» завершить сессию в Telegram."""
        with self._lock:
            self._reset()
            self._cancel_lock_timer()
            vault = self.vault
            if vault.unlocked() and vault.mode() == MODE_MEMORY and vault.get(KEY_SESSION):
                self._remote_logout()
            if vault.mode() is not None:
                vault.lock()

    def remove_legacy_files(self) -> LoginState:
        """Удалить открытые файлы сессии прежней версии."""
        with self._lock:
            self._remove_legacy()
            return self.status()

    # --- внутренности ---

    @staticmethod
    def _with_remote(state: LoginState, remote_failed: bool) -> LoginState:
        return LoginState(
            state.step,
            state.name,
            state.has_keys,
            remote_failed,
            state.mode,
            state.legacy,
            state.problem,
            state.two_factor,
        )

    def _remote_logout(self) -> bool:
        """Завершить сессию на стороне Telegram; True, если это не удалось."""
        saved = self.vault.get(KEY_SESSION)
        if not saved:
            return False
        try:
            credentials = self._credentials()
            loop = _LoopThread()
            try:
                loop.run(self._log_out(credentials, saved))
            finally:
                loop.stop()
        except Exception:  # noqa: BLE001 - локальный выход выполняется при любом отказе сети
            return True
        return False

    @staticmethod
    def _remove_legacy() -> None:
        for path in _legacy_files():
            _delete(path)

    @staticmethod
    def _error(exc: BaseException) -> TelegramLoginError:
        if isinstance(exc, TelegramLoginError):
            return exc
        if isinstance(exc, VaultError):
            return TelegramLoginError(exc.code, str(exc), **exc.params)
        if isinstance(exc, Exception):
            translated = _translate(exc)
            if translated is not None:
                return translated
        raise exc

    def _require_started(self) -> None:
        if self._client is None or self._loop is None:
            raise TelegramLoginError("login_not_started", "Сначала запросите код.")

    def _new_client(
        self, credentials: TelegramCredentials, saved: str, *, strict: bool = False
    ) -> Any:
        session = _string_session(saved, strict=strict)
        return self._factory(session, credentials.api_id, credentials.api_hash)

    async def _begin(self, credentials: TelegramCredentials, phone: str) -> LoginState:
        client = self._new_client(credentials, self.vault.get(KEY_SESSION) or "")
        self._client = client
        await client.connect()
        if await client.is_user_authorized():
            return await self._finish()
        sent = await client.send_code_request(phone)
        self._phone = phone
        self._phone_code_hash = sent.phone_code_hash
        return LoginState(STEP_NEED_CODE, mode=self.vault.mode())

    async def _submit_code(self, code: str) -> LoginState:
        from telethon import errors

        try:
            await self._client.sign_in(
                phone=self._phone, code=code, phone_code_hash=self._phone_code_hash
            )
        except errors.SessionPasswordNeededError:
            self._phone_code_hash = ""
            return LoginState(STEP_NEED_PASSWORD, mode=self.vault.mode())
        return await self._finish()

    async def _submit_password(self, password: str) -> LoginState:
        await self._client.sign_in(password=password)
        return await self._finish()

    async def _finish(self) -> LoginState:
        client = self._client
        me = await client.get_me()
        name = _full_name(me)
        saved = client.session.save()
        two_factor = await _two_factor_enabled(client)
        await client.disconnect()
        self._client = None
        vault = self.vault
        vault.set(KEY_SESSION, saved)
        vault.set(KEY_ACCOUNT, name)
        vault.set(KEY_TWO_FACTOR, None if two_factor is None else ("yes" if two_factor else "no"))
        self._remove_legacy()
        self._stop_loop_later()
        return LoginState(STEP_LOGGED_IN, name, True, mode=vault.mode(), two_factor=two_factor)

    async def _log_out(self, credentials: TelegramCredentials, saved: str) -> None:
        client = self._new_client(credentials, saved, strict=True)
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

    def _arm_lock_timer(self) -> None:
        """Хранилище с мастер-паролем закрывается само после долгого бездействия."""
        self._cancel_lock_timer()
        if self.vault.mode() == MODE_PASSWORD and self._lock_seconds > 0:
            self._lock_timer = threading.Timer(self._lock_seconds, self.lock)
            self._lock_timer.daemon = True
            self._lock_timer.start()

    def _cancel_lock_timer(self) -> None:
        if self._lock_timer is not None:
            self._lock_timer.cancel()
            self._lock_timer = None

    def _reset(self) -> None:
        """Закрыть клиент и цикл; в хранилище при этом ничего не меняется."""
        self._cancel_timer()
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
