"""Хранилище секретов (ключи Telegram API, сессия) с тремя режимами защиты.

- ``password`` (рекомендуемый): всё шифруется AES-256-GCM, ключ выводится из мастер-пароля
  алгоритмом scrypt. Пароль нигде не хранится; без него файл бесполезен даже для программы,
  запущенной под вашей учётной записью.
- ``dpapi``: шифрование Windows DPAPI. Удобно (пароль не нужен), но расшифровать может любой
  процесс этого же пользователя этого же компьютера.
- ``memory``: секреты живут только в памяти процесса и на диск не пишутся.

Свою криптографию здесь не пишем: AES-GCM даёт библиотека ``cryptography``, scrypt — стандартный
``hashlib``, DPAPI — системный вызов ``CryptProtectData`` через ``ctypes``. Расшифрованные секреты
доступны только пока хранилище разблокировано; ``lock()`` убирает их из памяти (насколько это
возможно в Python: строки неизменяемы и могут остаться в памяти до сборки мусора).
"""

import base64
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from chatstyle.errors import CodedError
from chatstyle.paths import data_dir

MODE_PASSWORD = "password"
MODE_DPAPI = "dpapi"
MODE_MEMORY = "memory"
MODES = (MODE_PASSWORD, MODE_DPAPI, MODE_MEMORY)

FORMAT_VERSION = 1
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**16, 8, 1  # около 64 МБ памяти и 0,3 с на попытку
SCRYPT_MAXMEM = 2**28
KEY_BYTES, SALT_BYTES, NONCE_BYTES = 32, 16, 12
DPAPI_ENTROPY = b"chatstyle-vault-v1"
FILE_NAME = "vault.json"
FREE_ATTEMPTS = 3  # после стольких неверных паролей подряд каждая попытка замедляется
MAX_BACKOFF_SECONDS = 8.0


class VaultError(CodedError):
    """Ошибка хранилища: код для перевода в окне; пароль и содержимое в тексте не встречаются."""


def vault_file() -> Path:
    return data_dir() / FILE_NAME


# --- права доступа ---


def system_tool(*parts: str) -> str:
    """Абсолютный путь к системной утилите Windows (System32): не по имени и не через PATH."""
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    return str(Path(root, "System32", *parts))


def _current_user_sid() -> str | None:
    """SID текущего пользователя Windows (через whoami); None, если определить не вышло."""
    try:
        result = subprocess.run(
            [system_tool("whoami.exe"), "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    fields = [item.strip('" ') for item in result.stdout.strip().split(",")]
    return fields[-1] if fields and fields[-1].startswith("S-1-") else None


def restrict_to_owner(path: Path) -> bool:
    """Оставить доступ к файлу или папке только текущему пользователю; False, если не удалось.

    Windows: отключается наследование прав и выдаётся полный доступ только пользователю (icacls).
    POSIX: права 0700 для папки и 0600 для файла.
    """
    if sys.platform != "win32":
        try:
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        except OSError:
            return False
        return True
    sid = _current_user_sid()
    if sid is None:
        return False
    grant = f"*{sid}:(OI)(CI)F" if path.is_dir() else f"*{sid}:F"
    try:
        result = subprocess.run(
            [system_tool("icacls.exe"), str(path), "/inheritance:r", "/grant:r", grant],
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def ensure_private_directory(path: Path) -> None:
    """Создать папку данных и закрыть её для остальных пользователей."""
    path.mkdir(parents=True, exist_ok=True)
    restrict_to_owner(path)


# --- DPAPI ---


class _DataBlob(ctypes.Structure):
    _fields_ = (("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char)))


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:  # type: ignore[type-arg]
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi(data: bytes, protect: bool) -> bytes:
    if not dpapi_available():
        raise VaultError("dpapi_unavailable", "DPAPI есть только в Windows.")
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32  # type: ignore[attr-defined]
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    source, keep_source = _blob(data)
    entropy, keep_entropy = _blob(DPAPI_ENTROPY)
    out = _DataBlob()
    ok = function(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN: никаких окон
        ctypes.byref(out),
    )
    del keep_source, keep_entropy
    if not ok:
        raise VaultError("vault_corrupt", "Не удалось расшифровать хранилище (DPAPI).")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


# --- шифрование по паролю ---


def _derive_key(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES, maxmem=SCRYPT_MAXMEM
    )


def _aad(header: dict) -> bytes:  # type: ignore[type-arg]
    return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Vault:
    """Хранилище строк по ключам; работает под замком, все методы потокобезопасны."""

    def __init__(self, path: Path | None = None, *, backoff: bool = True) -> None:
        self._path = path
        self._backoff = backoff
        self._lock = threading.RLock()
        self._mode: str | None = None
        self._data: dict[str, str] | None = None
        self._key: bytes | None = None
        self._kdf: dict[str, int | str] | None = None
        self._failures = 0

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else vault_file()

    # --- состояние ---

    def exists(self) -> bool:
        """Есть зашифрованный файл хранилища на диске."""
        return self.path.exists()

    def mode(self) -> str | None:
        """Режим: memory (создано в этом процессе), режим файла или None, если хранилища нет."""
        with self._lock:
            if self._mode is not None:
                return self._mode
            header = self._read_header()
            return header["mode"] if header else None

    def unlocked(self) -> bool:
        with self._lock:
            return self._data is not None

    def needs_password(self) -> bool:
        """Хранилище в режиме пароля и пока закрыто."""
        with self._lock:
            return self._data is None and self.mode() == MODE_PASSWORD

    # --- создание, открытие, закрытие ---

    def create(self, mode: str, password: str | None = None) -> None:
        """Создать новое пустое хранилище; существующий файл не перезаписывается."""
        with self._lock:
            if mode not in MODES:
                raise VaultError("vault_bad_mode", "Неизвестный режим хранения.")
            if self.exists() or self._data is not None:
                raise VaultError("vault_exists", "Хранилище уже создано.")
            self._mode = mode
            self._data = {}
            if mode == MODE_PASSWORD:
                self._set_password(password)
            if mode == MODE_DPAPI and not dpapi_available():
                self._reset()
                raise VaultError("dpapi_unavailable", "DPAPI есть только в Windows.")
            try:
                self._persist()
            except BaseException:
                self._reset()
                raise

    def unlock(self, password: str | None = None) -> None:
        """Расшифровать хранилище; неверный пароль — ошибка с растущей задержкой."""
        with self._lock:
            if self._data is not None:
                return
            header_and_body = self._read_file()
            if header_and_body is None:
                raise VaultError("vault_missing", "Хранилище не создано.")
            header, body = header_and_body
            mode = header["mode"]
            try:
                if mode == MODE_DPAPI:
                    plain = _dpapi(base64.b64decode(body["data"]), protect=False)
                    key = None
                elif mode == MODE_PASSWORD:
                    if not isinstance(password, str) or not password:
                        raise VaultError("vault_locked", "Нужен мастер-пароль.")
                    kdf = header["kdf"]
                    key = _derive_key(
                        password, base64.b64decode(kdf["salt"]), kdf["n"], kdf["r"], kdf["p"]
                    )
                    from cryptography.exceptions import InvalidTag
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

                    try:
                        plain = AESGCM(key).decrypt(
                            base64.b64decode(body["nonce"]),
                            base64.b64decode(body["data"]),
                            _aad(header),
                        )
                    except InvalidTag as exc:
                        raise VaultError("wrong_password", "Неверный мастер-пароль.") from exc
                else:
                    raise VaultError("vault_corrupt", "Неизвестный режим хранилища.")
                data = json.loads(plain.decode("utf-8"))
            except VaultError as exc:
                if exc.code == "wrong_password":
                    self._after_failure()
                raise
            except (ValueError, KeyError, TypeError) as exc:
                raise VaultError("vault_corrupt", "Файл хранилища повреждён.") from exc
            if not isinstance(data, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in data.items()
            ):
                raise VaultError("vault_corrupt", "Файл хранилища повреждён.")
            self._failures = 0
            self._mode = mode
            self._data = data
            self._key = key
            self._kdf = header.get("kdf")

    def lock(self) -> None:
        """Убрать секреты и ключ из памяти. Хранилище в режиме memory при этом теряется."""
        with self._lock:
            self._reset()

    def destroy(self) -> None:
        """Удалить файл хранилища и очистить память."""
        with self._lock:
            self._reset()
            for path in (self.path, self.path.with_name(self.path.name + ".tmp")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    # --- значения ---

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._require_data().get(key)

    def set(self, key: str, value: str | None) -> None:
        """Записать значение (None удаляет ключ) и сохранить хранилище."""
        with self._lock:
            data = self._require_data()
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
            self._persist()

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._require_data())

    # --- внутренности ---

    def _require_data(self) -> dict[str, str]:
        if self._data is None:
            raise VaultError("vault_locked", "Хранилище заблокировано.")
        return self._data

    def _reset(self) -> None:
        self._mode = None
        self._data = None
        self._key = None
        self._kdf = None

    def _set_password(self, password: str | None) -> None:
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            self._reset()
            raise VaultError(
                "password_weak", f"Мастер-пароль короче {MIN_PASSWORD_LENGTH} символов.", n=10
            )
        if len(password) > MAX_PASSWORD_LENGTH:
            self._reset()
            raise VaultError("password_weak", "Мастер-пароль слишком длинный.", n=10)
        salt = os.urandom(SALT_BYTES)
        self._kdf = {
            "name": "scrypt",
            "n": SCRYPT_N,
            "r": SCRYPT_R,
            "p": SCRYPT_P,
            "salt": base64.b64encode(salt).decode("ascii"),
        }
        self._key = _derive_key(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)

    def _after_failure(self) -> None:
        self._failures += 1
        if self._backoff and self._failures > FREE_ATTEMPTS:
            delay = min(0.5 * 2 ** (self._failures - FREE_ATTEMPTS - 1), MAX_BACKOFF_SECONDS)
            time.sleep(delay)

    def _read_file(self) -> tuple[dict, dict] | None:  # type: ignore[type-arg]
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise VaultError("vault_corrupt", "Файл хранилища повреждён.") from exc
        if (
            not isinstance(raw, dict)
            or raw.get("v") != FORMAT_VERSION
            or not isinstance(raw.get("mode"), str)
        ):
            raise VaultError("vault_corrupt", "Неизвестный формат хранилища.")
        header = {key: raw[key] for key in ("v", "mode", "kdf") if key in raw}
        return header, raw

    def _read_header(self) -> dict | None:  # type: ignore[type-arg]
        try:
            loaded = self._read_file()
        except VaultError:
            return None
        return loaded[0] if loaded else None

    def _persist(self) -> None:
        if self._mode == MODE_MEMORY:
            return
        plain = json.dumps(self._require_data(), ensure_ascii=False).encode("utf-8")
        header: dict = {"v": FORMAT_VERSION, "mode": self._mode}  # type: ignore[type-arg]
        body: dict = {}  # type: ignore[type-arg]
        if self._mode == MODE_DPAPI:
            body["data"] = base64.b64encode(_dpapi(plain, protect=True)).decode("ascii")
        else:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            header["kdf"] = self._kdf
            nonce = os.urandom(NONCE_BYTES)
            body["nonce"] = base64.b64encode(nonce).decode("ascii")
            body["data"] = base64.b64encode(
                AESGCM(self._key or b"").encrypt(nonce, plain, _aad(header))
            ).decode("ascii")
        path = self.path
        ensure_private_directory(path.parent)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps({**header, **body}, indent=2), encoding="utf-8")
        restrict_to_owner(temporary)
        os.replace(temporary, path)


_prompt: Callable[[], str | None] | None = None


def set_password_prompt(prompt: Callable[[], str | None] | None) -> None:
    """Задать, как спрашивать мастер-пароль в консоли (в окне пароль вводится в самом окне)."""
    global _prompt
    _prompt = prompt


def unlock_interactively(vault: Vault, attempts: int = 3) -> None:
    """Открыть хранилище, спросив мастер-пароль у пользователя, если это нужно и возможно."""
    if vault.unlocked() or not vault.exists():
        return
    if not vault.needs_password():
        vault.unlock()  # DPAPI открывается без пароля
        return
    if _prompt is None:
        raise VaultError("vault_locked", "Хранилище заблокировано: нужен мастер-пароль.")
    for attempt in range(attempts):
        try:
            vault.unlock(_prompt())
            return
        except VaultError as exc:
            if exc.code != "wrong_password" or attempt == attempts - 1:
                raise


_default: Vault | None = None
_default_lock = threading.Lock()


def default_vault() -> Vault:
    """Общее хранилище процесса: им пользуются и окно, и сбор из Telegram."""
    global _default
    with _default_lock:
        if _default is None:
            _default = Vault()
        return _default


def reset_default_vault(vault: Vault | None = None) -> None:
    """Подменить общее хранилище (для тестов) или сбросить его."""
    global _default
    with _default_lock:
        _default = vault
