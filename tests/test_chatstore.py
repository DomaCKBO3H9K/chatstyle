import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from chatstyle import chatstore
from chatstyle.cli import app
from chatstyle.collectors import collect
from chatstyle.errors import ChatstyleError
from chatstyle.gui.api import Api
from chatstyle.pipeline import run_comparison
from chatstyle.securestore import MODE_PASSWORD, Vault, reset_default_vault
from typer.testing import CliRunner

runner = CliRunner()


def record(sender: str, key: str, index: int, text: str | None = None) -> dict[str, object]:
    return {
        "id": index,
        "type": "message",
        "date": f"2024-03-0{1 + index % 5}T1{index % 10}:{index:02d}:00",
        "from": sender,
        "from_id": key,
        "text": text if text is not None else f"сообщение {index} от {sender} ну как бы",
    }


def export(
    path: Path, name: str | None = "Друзья", chat_id: int | None = 777, count: int = 12
) -> Path:
    records = []
    for index in range(count):
        records.append(record("Аня", "user1", index))
        records.append(record("Боря", "user2", index))
    data: dict[str, object] = {"messages": records}
    if name is not None:
        data["name"] = name
    if chat_id is not None:
        data["id"] = chat_id
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


PASSWORD = "правильный-пароль-123"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Каталог данных подменён и создано открытое хранилище: чаты шифруются, как в работе."""
    monkeypatch.setenv("CHATSTYLE_HOME", str(tmp_path / "home"))
    vault = Vault(tmp_path / "vault.json", backoff=False)
    vault.create(MODE_PASSWORD, PASSWORD)
    reset_default_vault(vault)
    yield tmp_path / "home"
    reset_default_vault(None)
    chatstore._MEMORY.clear()


def test_import_and_list(tmp_path: Path, home: Path) -> None:
    chat = chatstore.import_chat(export(tmp_path / "result.json"))
    assert (chat.id, chat.name, chat.messages) == ("777", "Друзья", 24)
    assert [(s.key, s.name, s.messages) for s in chat.senders] == [
        ("user1", "Аня", 12),
        ("user2", "Боря", 12),
    ]
    assert [item.id for item in chatstore.list_chats()] == ["777"]
    assert (home / "chats" / "777.chat").exists()


def test_empty_list_when_nothing_uploaded(home: Path) -> None:
    assert chatstore.list_chats() == []


def test_import_twice_does_not_duplicate_and_keeps_new_messages(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json", count=10))
    chat = chatstore.import_chat(export(tmp_path / "b.json", count=14))
    assert [s.messages for s in chat.senders] == [14, 14]
    again = chatstore.import_chat(export(tmp_path / "c.json", count=14))
    assert [s.messages for s in again.senders] == [14, 14]
    assert again.added == chat.added


def test_import_keeps_senders_missing_from_the_new_export(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    only_anya = tmp_path / "b.json"
    only_anya.write_text(
        json.dumps(
            {"name": "Друзья", "id": 777, "messages": [record("Аня", "user1", 99, "новое")]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    chat = chatstore.import_chat(only_anya)
    assert {s.key: s.messages for s in chat.senders} == {"user1": 13, "user2": 12}


def test_chat_without_id_gets_stable_id_from_name(tmp_path: Path, home: Path) -> None:
    first = chatstore.import_chat(export(tmp_path / "a.json", chat_id=None))
    second = chatstore.import_chat(export(tmp_path / "b.json", chat_id=None))
    assert first.id == second.id and first.id.startswith("x")
    assert len(chatstore.list_chats()) == 1


def test_import_of_empty_or_broken_export_fails(tmp_path: Path, home: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"messages": []}), encoding="utf-8")
    with pytest.raises(ChatstyleError, match="нет текстовых"):
        chatstore.import_chat(empty)
    broken = tmp_path / "broken.json"
    broken.write_text("{не json", encoding="utf-8")
    with pytest.raises(ChatstyleError):
        chatstore.import_chat(broken)
    assert chatstore.list_chats() == []


def test_get_chat_by_id_or_name_and_errors(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    assert chatstore.get_chat("777").name == "Друзья"
    assert chatstore.get_chat("друзья").id == "777"
    with pytest.raises(ChatstyleError, match="не найден"):
        chatstore.get_chat("нет такого")

    chatstore.import_chat(export(tmp_path / "b.json", chat_id=888))
    with pytest.raises(ChatstyleError, match="неоднозначно"):
        chatstore.get_chat("Друзья")
    assert chatstore.get_chat("888").id == "888"


def test_remove_chat(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    chatstore.remove_chat("Друзья")
    assert chatstore.list_chats() == []
    with pytest.raises(ChatstyleError):
        chatstore.remove_chat("777")


def test_read_sender_by_name_key_and_with_times(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    by_name = chatstore.read_chat_sender("777#Аня")
    assert len(by_name) == 12 and by_name.times is not None
    assert by_name.times == sorted(by_name.times)
    assert list(chatstore.read_chat_sender("друзья#user1")) == list(by_name)


def test_read_sender_errors(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    for bad in ("777", "#Аня", "777#", ""):
        with pytest.raises(ChatstyleError, match="Укажите чат и участника"):
            chatstore.read_chat_sender(bad)
    with pytest.raises(ChatstyleError, match="Участник"):
        chatstore.read_chat_sender("777#Вера")


def test_same_name_in_two_accounts_is_ambiguous(tmp_path: Path, home: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text(
        json.dumps(
            {
                "name": "Чат",
                "id": 5,
                "messages": [record("Саша", "user1", 1), record("Саша", "user2", 2)],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    chatstore.import_chat(path)
    with pytest.raises(ChatstyleError, match="неоднозначно"):
        chatstore.read_chat_sender("5#Саша")
    assert len(chatstore.read_chat_sender("5#user2")) == 1


def test_broken_or_foreign_files_are_ignored(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    folder = home / "chats"
    (folder / "junk.json").write_text("не json", encoding="utf-8")
    (folder / "old.json").write_text(json.dumps({"version": 0}), encoding="utf-8")
    assert [item.id for item in chatstore.list_chats()] == ["777"]


def test_collect_and_comparison_use_chat_source(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    assert len(collect("chat:777#Боря")) == 12
    result = run_comparison("chat:777#Аня", ["chat:Друзья#Боря"], rhythm=True)
    assert result.unknown.messages == 12
    assert result.candidates[0].label == "chat:Друзья#Боря"


def test_cli_chats_add_list_remove_and_compare(tmp_path: Path, home: Path) -> None:
    path = export(tmp_path / "result.json")
    added = runner.invoke(app, ["chats", "add", str(path)])
    assert added.exit_code == 0
    assert "Друзья" in added.output and "chat:777#" in added.output

    listing = runner.invoke(app, ["chats", "list"], env={"COLUMNS": "200"})
    assert listing.exit_code == 0 and "Друзья" in listing.output

    people = runner.invoke(app, ["chats", "list", "друзья"], env={"COLUMNS": "200"})
    assert people.exit_code == 0 and "Аня" in people.output and "user2" in people.output

    compare = runner.invoke(
        app,
        ["compare", "-u", "chat:777#Аня", "-c", "chat:777#Боря"],
        env={"COLUMNS": "200"},
    )
    assert compare.exit_code == 0 and "Неизвестный автор: chat:777#Аня" in compare.output

    removed = runner.invoke(app, ["chats", "remove", "777"])
    assert removed.exit_code == 0
    after = runner.invoke(app, ["chats", "list"])
    assert "Загруженных чатов нет" in after.output
    assert runner.invoke(app, ["chats", "remove", "777"]).exit_code == 2


def test_cli_chats_errors(tmp_path: Path, home: Path) -> None:
    assert runner.invoke(app, ["chats", "add", str(tmp_path / "нет.json")]).exit_code == 2
    assert runner.invoke(app, ["chats", "list", "нет такого"]).exit_code == 2


def test_api_lists_chats_and_builds_sources(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    api = Api()
    answer = api.chats_list()
    assert answer["state"] == "ok" and answer["memory"] is False
    chats = answer["chats"]
    assert [(c["id"], c["name"], c["messages"]) for c in chats] == [("777", "Друзья", 24)]
    assert [s["key"] for s in chats[0]["senders"]] == ["user1", "user2"]

    source = api.chat_source("777", "user1")
    assert source == {"spec": "chat:777#Аня", "label": "Друзья › Аня"}
    assert api.chat_source("777", "нет")["error"]["code"] == "sender_missing"
    assert api.chat_source("нет", "user1")["error"]["code"] == "chat_missing"
    assert api.chat_source(5, "user1")["error"]["code"] == "bad_input"  # type: ignore[arg-type]


def test_api_source_with_ambiguous_name_uses_the_key(tmp_path: Path, home: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text(
        json.dumps(
            {
                "name": "Чат",
                "id": 5,
                "messages": [record("Саша", "user1", 1), record("Саша", "user2", 2)],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    chatstore.import_chat(path)
    assert Api().chat_source("5", "user2")["spec"] == "chat:5#user2"


def test_api_remove_chat(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    api = Api()
    assert api.chats_remove("777") == {"ok": True}
    assert api.chats_remove("777")["error"]["code"] == "chat_missing"
    assert api.chats_remove(5)["error"]["code"] == "bad_input"  # type: ignore[arg-type]


def test_api_accepts_only_existing_chat_specs(tmp_path: Path, home: Path) -> None:
    chatstore.import_chat(export(tmp_path / "a.json"))
    api = Api()
    assert api._spec_allowed("chat:777#Аня") is True
    assert api._spec_allowed("chat:Друзья#user2") is True
    assert api._spec_allowed("chat:999#Аня") is False
    assert api._spec_allowed("chat:#Аня") is False
    assert api._spec_allowed("chat:777") is False
