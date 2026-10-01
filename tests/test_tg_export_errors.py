import json
from pathlib import Path

import pytest
from chatstyle.collectors.tg_export import read_tg_export
from chatstyle.errors import ChatstyleError

FIXTURES = Path(__file__).parent / "fixtures"
EXPORT = FIXTURES / "result.json"


def test_not_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("не json", encoding="utf-8")
    with pytest.raises(ChatstyleError) as exc:
        read_tg_export(path, "any")
    assert "JSON" in str(exc.value)


def test_no_messages_list(tmp_path: Path) -> None:
    path = tmp_path / "no_messages.json"
    path.write_text(json.dumps({"name": "x"}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ChatstyleError) as exc:
        read_tg_export(path, "any")
    assert "messages" in str(exc.value)


def test_all_chats_export(tmp_path: Path) -> None:
    path = tmp_path / "all_chats.json"
    path.write_text(json.dumps({"chats": {"list": []}}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ChatstyleError) as exc:
        read_tg_export(path, "any")
    assert "всех чатов" in str(exc.value)


def test_json_not_object(tmp_path: Path) -> None:
    path = tmp_path / "array.json"
    path.write_text(json.dumps([1, 2], ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ChatstyleError):
        read_tg_export(path, "any")


def test_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "does_not_exist.json"
    with pytest.raises(ChatstyleError):
        read_tg_export(path, "any")


def test_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "cp1251.json"
    path.write_bytes("привет".encode("cp1251"))
    with pytest.raises(ChatstyleError) as exc:
        read_tg_export(path, "any")
    assert "UTF-8" in str(exc.value)


def test_text_fragments_edge_cases(tmp_path: Path) -> None:
    data = {
        "messages": [
            {
                "type": "message",
                "from": "A",
                "from_id": "user1",
                "text": [
                    "a",
                    {"type": "bold", "text": "b"},
                    {"type": "x"},
                    5,
                    "c",
                ],
            }
        ]
    }
    path = tmp_path / "fragments.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = read_tg_export(path, "A")
    assert result == ["abc"]


def test_sender_without_text_messages(tmp_path: Path) -> None:
    data = {
        "messages": [
            {
                "type": "message",
                "from": "A",
                "from_id": "user1",
                "text": "",
            }
        ]
    }
    path = tmp_path / "empty_text.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = read_tg_export(path, "A")
    assert result == []


def test_null_from_is_ignored(tmp_path: Path) -> None:
    data = {
        "messages": [
            {
                "type": "message",
                "from": None,
                "from_id": "user9",
                "text": "x",
            },
            {
                "type": "message",
                "from": "A",
                "from_id": "user1",
                "text": "y",
            },
        ]
    }
    path = tmp_path / "null_from.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result_a = read_tg_export(path, "A")
    result_user9 = read_tg_export(path, "user9")
    assert result_a == ["y"]
    assert result_user9 == ["x"]
