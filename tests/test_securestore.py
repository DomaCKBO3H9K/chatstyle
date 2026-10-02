"""Хранилище секретов: шифрование по мастер-паролю, DPAPI, режим памяти, порча файла, права."""

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest
from chatstyle import securestore
from chatstyle.securestore import (
    MODE_DPAPI,
    MODE_MEMORY,
    MODE_PASSWORD,
    Vault,
    VaultError,
)

PASSWORD = "correct horse battery staple"
SECRET = "СЕКРЕТНАЯ-сессия-1234567890"


def make(tmp_path: Path, **kwargs: object) -> Vault:
    return Vault(tmp_path / "vault.json", backoff=False, **kwargs)  # type: ignore[arg-type]


def code_of(call) -> str:  # noqa: ANN001
    with pytest.raises(VaultError) as info:
        call()
    return info.value.code


# --- режим пароля ---


def test_password_vault_roundtrip_and_nothing_readable_on_disk(tmp_path: Path) -> None:
    vault = make(tmp_path)
    vault.create(MODE_PASSWORD, PASSWORD)
    vault.set("session", SECRET)
    vault.set("api_hash", "a" * 32)
    raw = vault.path.read_text(encoding="utf-8")
    for leaked in (
        SECRET,
        "a" * 32,
        PASSWORD,
        "session",
        "api_hash",
        base64.b64encode(SECRET.encode()).decode(),
    ):
        assert leaked not in raw
    vault.lock()
    assert not vault.unlocked() and vault.needs_password() and vault.mode() == MODE_PASSWORD
    assert code_of(lambda: vault.get("session")) == "vault_locked"
    vault.unlock(PASSWORD)
    assert vault.get("session") == SECRET and vault.keys() == ["api_hash", "session"]


def test_other_instance_can_open_the_file_with_the_right_password(tmp_path: Path) -> None:
    make(tmp_path).create(MODE_PASSWORD, PASSWORD)
    first = make(tmp_path)
    first.unlock(PASSWORD)
    first.set("k", "значение")
    second = make(tmp_path)
    assert second.mode() == MODE_PASSWORD and second.needs_password()
    second.unlock(PASSWORD)
    assert second.get("k") == "значение"


def test_wrong_and_empty_passwords_are_refused(tmp_path: Path) -> None:
    vault = make(tmp_path)
    vault.create(MODE_PASSWORD, PASSWORD)
    vault.lock()
    assert code_of(lambda: vault.unlock("wrong password!!")) == "wrong_password"
    assert code_of(lambda: vault.unlock(PASSWORD.upper())) == "wrong_password"
    assert code_of(lambda: vault.unlock("")) == "vault_locked"
    assert code_of(lambda: vault.unlock(None)) == "vault_locked"
    assert not vault.unlocked()
    vault.unlock(PASSWORD)
    assert vault.unlocked()


def test_weak_passwords_do_not_create_a_vault(tmp_path: Path) -> None:
    vault = make(tmp_path)
    for weak in (None, "", "short", "123456789", "x" * 300):
        assert code_of(lambda weak=weak: vault.create(MODE_PASSWORD, weak)) == "password_weak"
    assert not vault.path.exists() and vault.mode() is None and not vault.unlocked()


def test_second_create_never_overwrites(tmp_path: Path) -> None:
    vault = make(tmp_path)
    vault.create(MODE_PASSWORD, PASSWORD)
    vault.set("k", "v")
    before = vault.path.read_text(encoding="utf-8")
    assert code_of(lambda: vault.create(MODE_PASSWORD, PASSWORD + "2")) == "vault_exists"
    assert vault.path.read_text(encoding="utf-8") == before
    assert code_of(lambda: make(tmp_path).create(MODE_MEMORY)) == "vault_exists"


def test_unknown_mode_is_refused(tmp_path: Path) -> None:
    assert code_of(lambda: make(tmp_path).create("plain")) == "vault_bad_mode"
    assert not (tmp_path / "vault.json").exists()


def test_every_save_uses_a_fresh_nonce(tmp_path: Path) -> None:
    vault = make(tmp_path)
    vault.create(MODE_PASSWORD, PASSWORD)
    vault.set("k", "v")
    first = json.loads(vault.path.read_text(encoding="utf-8"))
    vault.set("k", "v")  # то же содержимое
    second = json.loads(vault.path.read_text(encoding="utf-8"))
    assert first["nonce"] != second["nonce"] and first["data"] != second["data"]
    assert first["kdf"]["salt"] == second["kdf"]["salt"]


def test_salt_differs_between_vaults(tmp_path: Path) -> None:
    one, two = Vault(tmp_path / "a.json", backoff=False), Vault(tmp_path / "b.json", backoff=False)
    one.create(MODE_PASSWORD, PASSWORD)
    two.create(MODE_PASSWORD, PASSWORD)
    salts = [json.loads(v.path.read_text(encoding="utf-8"))["kdf"]["salt"] for v in (one, two)]
    assert salts[0] != salts[1]


# --- подмена и порча файла ---


def _tamper(vault: Vault, change) -> None:  # noqa: ANN001
    document = json.loads(vault.path.read_text(encoding="utf-8"))
    change(document)
    vault.path.write_text(json.dumps(document), encoding="utf-8")


def _locked(tmp_path: Path) -> Vault:
    vault = make(tmp_path)
    vault.create(MODE_PASSWORD, PASSWORD)
    vault.set("session", SECRET)
    vault.lock()
    return vault


def test_flipped_ciphertext_is_detected(tmp_path: Path) -> None:
    vault = _locked(tmp_path)

    def flip(document: dict) -> None:
        body = bytearray(base64.b64decode(document["data"]))
        body[0] ^= 1
        document["data"] = base64.b64encode(bytes(body)).decode()

    _tamper(vault, flip)
    assert code_of(lambda: vault.unlock(PASSWORD)) == "wrong_password"
    assert not vault.unlocked()


def test_header_is_authenticated(tmp_path: Path) -> None:
    for field, value in (("v", 1), ("mode", "password")):  # те же значения: файл цел
        vault = _locked(tmp_path / field)
        _tamper(vault, lambda d, f=field, v=value: d.__setitem__(f, v))
        vault.unlock(PASSWORD)
    vault = _locked(tmp_path / "kdf")
    _tamper(vault, lambda d: d["kdf"].__setitem__("n", 2**15))  # слабее параметры: ключ не тот
    assert code_of(lambda: vault.unlock(PASSWORD)) == "wrong_password"


def test_swapping_the_salt_or_nonce_breaks_decryption(tmp_path: Path) -> None:
    vault = _locked(tmp_path)
    _tamper(vault, lambda d: d.__setitem__("nonce", base64.b64encode(b"\x00" * 12).decode()))
    assert code_of(lambda: vault.unlock(PASSWORD)) == "wrong_password"


@pytest.mark.parametrize(
    "garbage",
    ["", "не json", "[1, 2]", '{"v": 2, "mode": "password"}', '{"v": 1}', '{"v": 1, "mode": "x"}'],
)
def test_broken_files_report_corruption_and_never_crash(tmp_path: Path, garbage: str) -> None:
    vault = make(tmp_path)
    vault.path.write_text(garbage, encoding="utf-8")
    assert code_of(lambda: vault.unlock(PASSWORD)) == "vault_corrupt"
    assert not vault.unlocked()
    assert vault.mode() is None or garbage.startswith('{"v": 1, "mode"')


def test_non_string_contents_are_refused(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    vault = _locked(tmp_path)
    document = json.loads(vault.path.read_text(encoding="utf-8"))
    kdf = document["kdf"]
    key = securestore._derive_key(
        PASSWORD, base64.b64decode(kdf["salt"]), kdf["n"], kdf["r"], kdf["p"]
    )
    header = {"v": document["v"], "mode": document["mode"], "kdf": kdf}
    nonce = b"\x01" * 12
    forged = AESGCM(key).encrypt(nonce, b'{"k": 5}', securestore._aad(header))
    document["nonce"] = base64.b64encode(nonce).decode()
    document["data"] = base64.b64encode(forged).decode()
    vault.path.write_text(json.dumps(document), encoding="utf-8")
    assert code_of(lambda: vault.unlock(PASSWORD)) == "vault_corrupt"


def test_missing_file_is_reported(tmp_path: Path) -> None:
    vault = make(tmp_path)
    assert code_of(lambda: vault.unlock(PASSWORD)) == "vault_missing"
    assert vault.mode() is None and not vault.exists()


# --- замедление подбора ---


def test_wrong_passwords_slow_down_after_a_few_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    delays: list[float] = []
    monkeypatch.setattr(securestore.time, "sleep", delays.append)
    vault = Vault(tmp_path / "vault.json", backoff=True)
    vault.create(MODE_PASSWORD, PASSWORD)
    vault.lock()
    for _ in range(6):
        code_of(lambda: vault.unlock("wrong password!!"))
    assert delays == [0.5, 1.0, 2.0]
    vault.unlock(PASSWORD)
    vault.lock()
    code_of(lambda: vault.unlock("wrong password!!"))
    assert delays == [0.5, 1.0, 2.0]  # счётчик сброшен успешным входом


def test_the_delay_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr(securestore.time, "sleep", delays.append)
    vault = Vault(tmp_path / "vault.json", backoff=True)
    vault.create(MODE_PASSWORD, PASSWORD)
    vault.lock()
    for _ in range(14):
        code_of(lambda: vault.unlock("wrong password!!"))
    assert max(delays) == securestore.MAX_BACKOFF_SECONDS


# --- режим памяти ---


def test_memory_mode_never_touches_the_disk(tmp_path: Path) -> None:
    vault = make(tmp_path)
    vault.create(MODE_MEMORY)
    vault.set("session", SECRET)
    assert vault.get("session") == SECRET and vault.mode() == MODE_MEMORY and vault.unlocked()
    assert not vault.exists() and list(tmp_path.iterdir()) == []
    vault.lock()
    assert vault.mode() is None and not vault.unlocked()
    assert code_of(lambda: vault.get("session")) == "vault_locked"


def test_destroy_removes_the_file_and_the_memory(tmp_path: Path) -> None:
    vault = _locked(tmp_path)
    vault.unlock(PASSWORD)
    vault.destroy()
    assert not vault.path.exists() and vault.mode() is None and not vault.unlocked()
    assert list(tmp_path.iterdir()) == []
    vault.destroy()  # повторное удаление безопасно


def test_set_none_removes_a_key(tmp_path: Path) -> None:
    vault = make(tmp_path)
    vault.create(MODE_PASSWORD, PASSWORD)
    vault.set("a", "1")
    vault.set("a", None)
    vault.lock()
    vault.unlock(PASSWORD)
    assert vault.get("a") is None and vault.keys() == []


def test_a_failed_write_leaves_the_old_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _locked(tmp_path)
    vault.unlock(PASSWORD)
    before = vault.path.read_text(encoding="utf-8")

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("диск полон")

    monkeypatch.setattr(securestore.os, "replace", boom)
    with pytest.raises(OSError):
        vault.set("x", "y")
    assert vault.path.read_text(encoding="utf-8") == before


# --- DPAPI ---


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI есть только в Windows")
def test_dpapi_roundtrip_and_no_plaintext_on_disk(tmp_path: Path) -> None:
    vault = make(tmp_path)
    vault.create(MODE_DPAPI)
    vault.set("session", SECRET)
    raw = vault.path.read_text(encoding="utf-8")
    assert SECRET not in raw and base64.b64encode(SECRET.encode()).decode() not in raw
    fresh = make(tmp_path)
    assert fresh.mode() == MODE_DPAPI and not fresh.needs_password()
    fresh.unlock()
    assert fresh.get("session") == SECRET


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI есть только в Windows")
def test_dpapi_blob_corruption_is_reported(tmp_path: Path) -> None:
    vault = make(tmp_path)
    vault.create(MODE_DPAPI)
    vault.set("k", "v")
    vault.lock()

    def damage(document: dict) -> None:
        body = bytearray(base64.b64decode(document["data"]))
        body[-1] ^= 0xFF
        document["data"] = base64.b64encode(bytes(body)).decode()

    _tamper(vault, damage)
    assert code_of(vault.unlock) == "vault_corrupt"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI есть только в Windows")
def test_dpapi_uses_our_entropy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = make(tmp_path)
    vault.create(MODE_DPAPI)
    vault.set("k", "v")
    vault.lock()
    monkeypatch.setattr(securestore, "DPAPI_ENTROPY", "другая энтропия".encode())
    assert (
        code_of(vault.unlock) == "vault_corrupt"
    )  # блоб, защищённый другим приложением, не открыть


def test_dpapi_is_refused_on_other_platforms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(securestore.sys, "platform", "linux")
    vault = make(tmp_path)
    assert code_of(lambda: vault.create(MODE_DPAPI)) == "dpapi_unavailable"
    assert not vault.path.exists() and vault.mode() is None


# --- права и общее хранилище ---


@pytest.mark.skipif(sys.platform != "win32", reason="icacls есть только в Windows")
def test_directory_is_closed_to_other_users(tmp_path: Path) -> None:
    target = tmp_path / "private"
    securestore.ensure_private_directory(target)
    shown = subprocess.run(["icacls", str(target)], capture_output=True, text=True).stdout
    sid = securestore._current_user_sid()
    assert sid is not None
    for group in (
        "Everyone",
        "BUILTIN\\Users",
        "Authenticated Users",
        "NT AUTHORITY\\Authenticated",
    ):
        assert group not in shown, shown
    vault = Vault(target / "vault.json", backoff=False)
    vault.create(MODE_PASSWORD, PASSWORD)
    shown_file = subprocess.run(["icacls", str(vault.path)], capture_output=True, text=True).stdout
    assert "Everyone" not in shown_file and "BUILTIN\\Users" not in shown_file
    assert vault.path.read_text(encoding="utf-8")  # владелец по-прежнему читает


@pytest.mark.skipif(sys.platform == "win32", reason="права POSIX")
def test_posix_permissions(tmp_path: Path) -> None:
    vault = Vault(tmp_path / "d" / "vault.json", backoff=False)
    vault.create(MODE_PASSWORD, PASSWORD)
    assert (vault.path.stat().st_mode & 0o777) == 0o600
    assert (vault.path.parent.stat().st_mode & 0o777) == 0o700


def test_default_vault_is_shared_and_replaceable(tmp_path: Path) -> None:
    securestore.reset_default_vault(None)
    first = securestore.default_vault()
    assert securestore.default_vault() is first
    mine = make(tmp_path)
    securestore.reset_default_vault(mine)
    assert securestore.default_vault() is mine
    securestore.reset_default_vault(None)


def test_error_messages_never_contain_secrets(tmp_path: Path) -> None:
    vault = make(tmp_path)
    vault.create(MODE_PASSWORD, PASSWORD)
    vault.set("session", SECRET)
    vault.lock()
    try:
        vault.unlock("wrong password!!")
    except VaultError as exc:
        text = f"{exc} {exc.params} {exc.code}"
    assert PASSWORD not in text and SECRET not in text and "wrong password" not in text


def test_system_tools_are_absolute_paths_not_path_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SystemRoot", r"C:\Win")
    path = securestore.system_tool("icacls.exe")
    assert Path(path).is_absolute() or path.startswith("C:")
    assert path.replace("/", "\\").lower() == r"c:\win\system32\icacls.exe"
    source = (Path(securestore.__file__)).read_text(encoding="utf-8")
    assert '"icacls",' not in source and '"whoami",' not in source  # никаких имён без пути
