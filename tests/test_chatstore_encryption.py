import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from chatstyle import chatcrypt, chatstore
from chatstyle.errors import CodedError
from chatstyle.gui.api import Api
from chatstyle.securestore import (
    MODE_MEMORY,
    MODE_PASSWORD,
    Vault,
    reset_default_vault,
)

PASSWORD = "правильный-пароль-123"
SECRET = "уникальная-фраза-для-поиска-в-файле"


def write_export(path: Path, chat_id: int = 777, text: str = SECRET) -> Path:
    records = [
        {
            "id": index,
            "type": "message",
            "date": f"2024-03-0{1 + index % 5}T12:{index:02d}:00",
            "from": "Аня",
            "from_id": "user1",
            "text": f"{text} {index}",
        }
        for index in range(6)
    ]
    path.write_text(
        json.dumps({"name": "Друзья", "id": chat_id, "messages": records}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("CHATSTYLE_HOME", str(tmp_path / "home"))
    yield tmp_path / "home"
    reset_default_vault(None)
    chatstore._MEMORY.clear()


def password_vault(tmp_path: Path, create: bool = True) -> Vault:
    vault = Vault(tmp_path / "vault.json", backoff=False)
    if create:
        vault.create(MODE_PASSWORD, PASSWORD)
    reset_default_vault(vault)
    return vault


def test_chat_is_stored_encrypted_and_plaintext_is_not_on_disk(tmp_path: Path, home: Path) -> None:
    password_vault(tmp_path)
    chatstore.import_chat(write_export(tmp_path / "a.json"))
    files = sorted(path.name for path in (home / "chats").iterdir())
    assert files == ["777.chat"]
    blob = (home / "chats" / "777.chat").read_bytes()
    assert blob.startswith(chatcrypt.MAGIC)
    assert SECRET.encode("utf-8") not in blob and "Аня".encode() not in blob
    assert SECRET.encode("utf-8") not in (tmp_path / "vault.json").read_bytes()


def test_key_lives_in_the_vault_and_is_reused(tmp_path: Path, home: Path) -> None:
    vault = password_vault(tmp_path)
    assert vault.get(chatstore.VAULT_KEY) is None
    chatstore.import_chat(write_export(tmp_path / "a.json"))
    key = vault.get(chatstore.VAULT_KEY)
    assert key is not None and len(chatcrypt.decode_key(key)) == chatcrypt.KEY_SIZE
    chatstore.import_chat(write_export(tmp_path / "b.json", chat_id=888))
    assert vault.get(chatstore.VAULT_KEY) == key  # ключ не меняется


def test_chats_survive_a_restart_with_the_right_password(tmp_path: Path, home: Path) -> None:
    password_vault(tmp_path)
    chatstore.import_chat(write_export(tmp_path / "a.json"))
    reopened = password_vault(tmp_path, create=False)  # «новый запуск»: хранилище закрыто
    with pytest.raises(CodedError) as locked:
        chatstore.list_chats()
    assert locked.value.code == "chats_locked"
    reopened.unlock(PASSWORD)
    assert [chat.id for chat in chatstore.list_chats()] == ["777"]
    assert len(chatstore.read_chat_sender("777#Аня")) == 6


def test_no_vault_means_setup_is_needed(tmp_path: Path, home: Path) -> None:
    password_vault(tmp_path, create=False)
    with pytest.raises(CodedError) as setup:
        chatstore.import_chat(write_export(tmp_path / "a.json"))
    assert setup.value.code == "chats_setup"
    assert not (home / "chats").exists()  # ничего открытого не сохранено


def test_legacy_plain_files_are_encrypted_on_first_open(tmp_path: Path, home: Path) -> None:
    password_vault(tmp_path)
    data = {
        "version": 1,
        "id": "5",
        "name": "Старый",
        "added": "2024-01-01",
        "updated": "2024-01-02",
        "senders": {"u": {"name": "Аня", "messages": [SECRET], "times": [100]}},
    }
    folder = home / "chats"
    folder.mkdir(parents=True)
    (folder / "5.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    chats = chatstore.list_chats()
    assert [(c.id, c.name, c.added) for c in chats] == [("5", "Старый", "2024-01-01")]
    assert sorted(path.name for path in folder.iterdir()) == ["5.chat"]  # открытой копии нет
    assert SECRET.encode("utf-8") not in (folder / "5.chat").read_bytes()
    assert list(chatstore.read_chat_sender("5#u")) == [SECRET]


def test_tampered_or_swapped_files_are_rejected(tmp_path: Path, home: Path) -> None:
    password_vault(tmp_path)
    chatstore.import_chat(write_export(tmp_path / "a.json", chat_id=1))
    chatstore.import_chat(write_export(tmp_path / "b.json", chat_id=2))
    folder = home / "chats"

    swapped = (folder / "1.chat").read_bytes()
    (folder / "2.chat").write_bytes(swapped)  # чужой файл под другим именем (привязка к id)
    with pytest.raises(CodedError) as swap:
        chatstore.list_chats()
    assert swap.value.code == "chat_decrypt"

    blob = bytearray((folder / "1.chat").read_bytes())
    blob[-1] ^= 1
    (folder / "1.chat").write_bytes(bytes(blob))
    (folder / "2.chat").unlink()
    with pytest.raises(CodedError) as tamper:
        chatstore.list_chats()
    assert tamper.value.code == "chat_decrypt"


def test_wrong_key_in_the_vault_cannot_read_existing_chats(tmp_path: Path, home: Path) -> None:
    vault = password_vault(tmp_path)
    chatstore.import_chat(write_export(tmp_path / "a.json"))
    vault.set(chatstore.VAULT_KEY, chatcrypt.encode_key(chatcrypt.new_key()))
    with pytest.raises(CodedError) as error:
        chatstore.list_chats()
    assert error.value.code == "chat_decrypt"
    vault.set(chatstore.VAULT_KEY, "не ключ")
    with pytest.raises(CodedError) as broken:
        chatstore.list_chats()
    assert broken.value.code == "chat_key_invalid"


def test_remove_wipes_the_file(tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    password_vault(tmp_path)
    chatstore.import_chat(write_export(tmp_path / "a.json"))
    wiped: list[str] = []
    real = chatcrypt.wipe_file
    monkeypatch.setattr(chatcrypt, "wipe_file", lambda path: (wiped.append(path.name), real(path)))
    chatstore.remove_chat("777")
    assert "777.chat" in wiped
    assert list((home / "chats").iterdir()) == []


def test_memory_mode_keeps_chats_only_in_memory(tmp_path: Path, home: Path) -> None:
    vault = Vault(tmp_path / "vault.json", backoff=False)
    vault.create(MODE_MEMORY)
    reset_default_vault(vault)
    chatstore.import_chat(write_export(tmp_path / "a.json"))
    assert [chat.id for chat in chatstore.list_chats()] == ["777"]
    assert len(chatstore.read_chat_sender("Друзья#Аня")) == 6
    assert not (home / "chats").exists()  # на диск ничего не записано
    chatstore._MEMORY.clear()  # «закрыли окно»
    assert chatstore.list_chats() == []


def test_memory_copies_are_isolated(tmp_path: Path, home: Path) -> None:
    vault = Vault(tmp_path / "vault.json", backoff=False)
    vault.create(MODE_MEMORY)
    reset_default_vault(vault)
    chatstore.import_chat(write_export(tmp_path / "a.json"))
    messages = chatstore.read_chat_sender("777#Аня")
    messages.append("лишнее")
    assert len(chatstore.read_chat_sender("777#Аня")) == 6


def test_explicit_key_and_plain_modes_for_tools(tmp_path: Path) -> None:
    folder = tmp_path / "tool"
    chatstore.import_chat(write_export(tmp_path / "a.json"), folder)  # без ключа: открытый JSON
    assert [path.name for path in folder.iterdir()] == ["777.json"]
    key = chatcrypt.new_key()
    chatstore.import_chat(write_export(tmp_path / "b.json", chat_id=9), folder, key=key)
    assert sorted(path.name for path in folder.iterdir()) == ["777.json", "9.chat"]
    assert [c.id for c in chatstore.list_chats(folder)] == ["777"]  # без ключа .chat не виден
    assert sorted(c.id for c in chatstore.list_chats(folder, key=key)) == ["777", "9"]


def test_api_reports_locked_setup_ok_and_memory(tmp_path: Path, home: Path) -> None:
    api = Api()
    password_vault(tmp_path, create=False)
    assert api.chats_list() == {"state": "setup", "chats": [], "memory": False, "legacy": 0}

    vault = password_vault(tmp_path)
    chatstore.import_chat(write_export(tmp_path / "a.json"))
    vault.lock()
    locked = api.chats_list()
    assert locked["state"] == "locked" and locked["chats"] == []
    vault.unlock(PASSWORD)
    assert api.chats_list()["state"] == "ok"

    other = Vault(tmp_path / "memory-vault.json", backoff=False)
    other.create(MODE_MEMORY)
    reset_default_vault(other)
    assert api.chats_list() == {"state": "ok", "chats": [], "memory": True, "legacy": 0}


def test_api_errors_are_coded_for_translation(tmp_path: Path, home: Path) -> None:
    password_vault(tmp_path, create=False)
    api = Api()
    assert api.chat_source("777", "user1")["error"]["code"] == "chats_setup"
    assert api.chats_remove("777")["error"]["code"] == "chats_setup"
    assert api._spec_allowed("chat:777#Аня") is False


def test_api_warns_about_plain_legacy_files_in_memory_mode(tmp_path: Path, home: Path) -> None:
    legacy = {
        "version": 1,
        "id": "5",
        "name": "Старый",
        "added": "2024-01-01",
        "updated": "2024-01-02",
        "senders": {"u": {"name": "Аня", "messages": [SECRET], "times": [100]}},
    }
    folder = home / "chats"
    folder.mkdir(parents=True)
    (folder / "5.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    other = Vault(tmp_path / "memory-vault.json", backoff=False)
    other.create(MODE_MEMORY)
    reset_default_vault(other)
    answer = Api().chats_list()
    assert answer["state"] == "ok" and answer["chats"] == [] and answer["legacy"] == 1
    assert (folder / "5.json").exists()  # в режиме памяти открытые файлы не трогаются

    password_vault(tmp_path)  # выбрали мастер-пароль: открытые файлы шифруются
    after = Api().chats_list()
    assert [chat["id"] for chat in after["chats"]] == ["5"] and after["legacy"] == 0
    assert sorted(path.name for path in folder.iterdir()) == ["5.chat"]
