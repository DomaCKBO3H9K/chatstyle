import json
from pathlib import Path

import pytest
from chatstyle import chatstore
from synthetic import casual, formal, other

from experiments import chats_eval

STYLES = {
    "user1": lambda seed: casual(seed, 120),
    "user2": lambda seed: formal(seed, 120),
    "user3": lambda seed: other(0, seed, 120),
    "user4": lambda seed: other(2, seed, 120),
}


def write_export(path: Path, chat_id: int, name: str, seed: int) -> Path:
    records = []
    for number, (person, make) in enumerate(STYLES.items(), start=1):
        for index, line in enumerate(make(seed + number)):
            records.append(
                {
                    "id": len(records),
                    "type": "message",
                    "date": f"2024-03-{1 + index % 9:02d}T1{number}:{index % 60:02d}:00",
                    "from": person,
                    "from_id": person,
                    "text": line,
                }
            )
    path.write_text(
        json.dumps({"name": name, "id": chat_id, "messages": records}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def chats(tmp_path: Path) -> Path:
    folder = tmp_path / "chats"
    chatstore.import_chat(write_export(tmp_path / "a.json", 1, "Первый", 10), folder)
    chatstore.import_chat(write_export(tmp_path / "b.json", 2, "Второй", 100), folder)
    return folder


def test_cross_context_tasks_cover_every_person_and_chat(chats: Path) -> None:
    data = chats_eval.load_people(chats)
    tasks = chats_eval.build_tasks(data, min_words=600, time_messages=30, time_tasks=2)
    cross = [task for task in tasks if task.kind == "cross"]
    assert len(cross) == 8  # 4 человека × 2 чата
    for task in cross:
        assert task.person in task.candidates and len(task.candidates) == 4
    assert {task.kind for task in tasks} == {"cross", "time"}


def test_time_tasks_hold_out_the_last_messages(chats: Path) -> None:
    data = chats_eval.load_people(chats)
    tasks = chats_eval.build_tasks(data, min_words=600, time_messages=30, time_tasks=1)
    (task,) = [item for item in tasks if item.kind == "time"]
    assert task.person in task.candidates
    assert len(task.unknown) <= 30  # не больше held-out части (и не больше предела слов)


def test_no_person_is_compared_with_text_from_the_unknown_chat(chats: Path) -> None:
    data = chats_eval.load_people(chats)
    for task in chats_eval.build_tasks(data, min_words=600, time_messages=30):
        if task.kind != "cross":
            continue
        unknown_texts = set(task.unknown)
        for candidate in task.candidates.values():
            assert unknown_texts.isdisjoint(set(candidate))


def test_distinct_styles_are_recognized_in_both_modes(chats: Path) -> None:
    data = chats_eval.load_people(chats)
    tasks = chats_eval.build_tasks(data, min_words=600, time_messages=30, time_tasks=2)
    for lexical in (False, True):
        summary = chats_eval.evaluate(tasks, lexical)
        assert summary.tasks == len(tasks)
        assert summary.top1 == pytest.approx(1.0)
        assert summary.mrr == pytest.approx(1.0)
        assert summary.chance == pytest.approx(0.25)


def test_evaluate_without_tasks() -> None:
    assert chats_eval.evaluate([], False) == chats_eval.Summary(0, 0.0, 0.0, 0.0)


def test_main_prints_only_numbers(chats: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = chats_eval.main(["--chats-dir", str(chats), "--min-words", "600", "--time-tasks", "0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "стилевая смесь, через контексты: задач 8, top1 1.00" in out
    assert "user" not in out and "Первый" not in out  # ни идентификаторов, ни названий


def test_main_with_lexical_flag_and_when_there_is_nothing_to_check(
    chats: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert chats_eval.main(["--chats-dir", str(chats), "--min-words", "600", "--lexical"]) == 0
    assert "с лексикой" in capsys.readouterr().out
    assert chats_eval.main(["--chats-dir", str(tmp_path / "пусто")]) == 1
    assert "Не нашлось ни одной задачи" in capsys.readouterr().out


def test_main_reads_the_encrypted_store_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from chatstyle.securestore import MODE_PASSWORD, Vault, reset_default_vault

    monkeypatch.setenv("CHATSTYLE_HOME", str(tmp_path / "home"))
    vault = Vault(tmp_path / "vault.json", backoff=False)
    vault.create(MODE_PASSWORD, "правильный-пароль-123")
    reset_default_vault(vault)
    try:
        chatstore.import_chat(write_export(tmp_path / "a.json", 1, "Первый", 10))
        chatstore.import_chat(write_export(tmp_path / "b.json", 2, "Второй", 100))
        assert {p.suffix for p in (tmp_path / "home" / "chats").iterdir()} == {".chat"}
        code = chats_eval.main(["--min-words", "600", "--time-tasks", "0"])
        assert code == 0
        assert "через контексты: задач 8, top1 1.00" in capsys.readouterr().out
    finally:
        reset_default_vault(None)
