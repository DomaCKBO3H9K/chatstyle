"""Тесты для api.py: методы, которые вызывает веб-интерфейс pywebview."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from chatstyle.delta import DeltaScore
from chatstyle.features import FEATURE_LABELS
from chatstyle.gui import api as gui_api
from chatstyle.gui.model import CompareOutcome
from chatstyle.impostors import ImpostorsScore
from chatstyle.pipeline import (
    METHOD_IMPOSTORS,
    AuthorStats,
    CandidateResult,
    ComparisonResult,
)


def _write_lines(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _similar_lines() -> list[str]:
    return [f"Сегодня я хочу рассказать о том, как проверяется стиль автора {i}" for i in range(60)]


def _different_lines() -> list[str]:
    return [f"1234567890 абв где это я гулял {i}" for i in range(60)]


def _wait(api: gui_api.Api, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = api.poll()
        if state["state"] in ("done", "error"):
            return state
        time.sleep(0.02)
    raise AssertionError("Таймаут ожидания результата")


def test_init_disclaimer_and_version() -> None:
    api = gui_api.Api()
    data = api.init()
    assert data["disclaimer"]
    assert data["version"]


def test_start_compare_invalid() -> None:
    api = gui_api.Api()
    resp = api.start_compare(
        {
            "unknown": "",
            "candidates": [],
            "impostors_dir": "",
            "seed": "abc",
            "report_path": "",
        }
    )
    assert resp["ok"] is False
    codes = [item["code"] for item in resp["errors"]]
    assert codes == ["unknown_missing", "no_candidates", "bad_seed"]
    assert all(item["params"] == {} for item in resp["errors"])


def test_start_compare_error_params_are_strings(tmp_path: Path) -> None:
    api = gui_api.Api(allowed_paths=["a.txt", "b.txt", str(tmp_path / "нет")])
    resp = api.start_compare(
        {
            "unknown": "file:a.txt",
            "candidates": ["file:a.txt", "file:b.txt", "file:b.txt"],
            "impostors_dir": str(tmp_path / "нет"),
            "seed": "-3",
            "report_path": "",
        }
    )
    assert [item["code"] for item in resp["errors"]] == [
        "same_as_unknown",
        "duplicate_candidate",
        "bad_seed",
        "impostors_dir_missing",
    ]
    assert resp["errors"][1]["params"] == {"spec": "file:b.txt"}
    assert resp["errors"][3]["params"] == {"path": str(tmp_path / "нет")}


def test_full_compare(tmp_path: Path) -> None:
    similar = _write_lines(tmp_path / "similar.txt", _similar_lines())
    different = _write_lines(tmp_path / "different.txt", _different_lines())
    unknown = _write_lines(tmp_path / "unknown.txt", _similar_lines())

    api = gui_api.Api(allowed_paths=[unknown, similar, different])
    resp = api.start_compare(
        {
            "unknown": f"file:{unknown}",
            "candidates": [f"file:{similar}", f"file:{different}"],
            "impostors_dir": "",
            "seed": "1",
            "report_path": "",
        }
    )
    assert resp["ok"] is True
    state = _wait(api)
    assert state["state"] == "done"
    view = state["view"]
    assert view["candidates"][0]["label"] == "similar.txt"
    value = view["candidates"][0]["value"]
    assert 0 <= value <= 1
    assert view["metric"] == "cosine"
    assert view["notes"][0] == {"code": "ranking", "method": "cosine"}
    assert view["warning"]["min"] == 1000
    assert {"who": None, "words": view["warning"]["sides"][0]["words"]} == view["warning"]["sides"][
        0
    ]
    assert view["unknown"]["label"] == "unknown.txt"
    assert "summary" not in view and "metric_name" not in view  # фраз в ответе нет, только коды
    assert view["candidates"][0]["why"]
    assert not view["candidates"][1]["why"]
    assert api.poll() == {"state": "idle"}


def test_second_start_while_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    similar = _write_lines(tmp_path / "similar.txt", _similar_lines())
    unknown = _write_lines(tmp_path / "unknown.txt", _similar_lines())

    def blocking_run_compare(form):  # noqa: ANN001, ANN202
        time.sleep(10)
        raise AssertionError

    monkeypatch.setattr(gui_api, "run_compare", blocking_run_compare)
    api = gui_api.Api(allowed_paths=[unknown, similar])
    form = {
        "unknown": f"file:{unknown}",
        "candidates": [f"file:{similar}"],
        "impostors_dir": "",
        "seed": "1",
        "report_path": "",
    }
    first = api.start_compare(form)
    assert first["ok"] is True
    second = api.start_compare(form)
    assert second["ok"] is False
    assert second["errors"] == [{"code": "busy", "params": {}}]
    assert api.start_profile("file:x.txt")["errors"][0]["code"] == "busy"


def test_compare_error(tmp_path: Path) -> None:
    unknown = _write_lines(tmp_path / "unknown.txt", _similar_lines())
    api = gui_api.Api(allowed_paths=[unknown, tmp_path / "missing.txt"])
    resp = api.start_compare(
        {
            "unknown": f"file:{unknown}",
            "candidates": [f"file:{tmp_path / 'missing.txt'}"],
            "impostors_dir": "",
            "seed": "",
            "report_path": "",
        }
    )
    assert resp["ok"] is True
    state = _wait(api)
    assert state["state"] == "error"
    assert state["error"]["code"] == "core"
    assert state["error"]["params"]["message"]  # русский текст ядра — подробность


def test_start_profile(tmp_path: Path) -> None:
    author = _write_lines(tmp_path / "author.txt", _similar_lines())
    api = gui_api.Api(allowed_paths=[author])
    resp = api.start_profile(f"file:{author}")
    assert resp["ok"] is True
    state = _wait(api)
    assert state["state"] == "done"
    view = state["view"]
    assert view["label"] == "author.txt"
    assert view["words"] > 0 and view["messages"] == 60
    assert [item["key"] for item in view["features"]] == list(FEATURE_LABELS)
    assert [group["kind"] for group in view["word_lists"]] == ["fw", "fl", "ms"]
    assert all(
        set(item) == {"word", "value"} for group in view["word_lists"] for item in group["items"]
    )


def test_start_profile_without_source() -> None:
    assert gui_api.Api().start_profile("  ")["errors"] == [{"code": "source_missing", "params": {}}]


def test_pick_file() -> None:
    class FakeWindow:
        def __init__(self, result):
            self.result = result

        def create_file_dialog(self, kind, **kwargs):  # noqa: ANN001, ANN201
            self.kind = kind
            return self.result

    api = gui_api.Api(lambda: FakeWindow(None))
    assert api.pick_file() is None

    api2 = gui_api.Api(lambda: FakeWindow((str(Path("/tmp/file.txt")),)))
    res2 = api2.pick_file()
    assert res2["spec"] == f"file:{Path('/tmp/file.txt')}"
    assert res2["label"] == "file.txt"


def test_tg_source_unknown_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSender:
        def __init__(self, key, name):  # noqa: ANN001, ANN002
            self.key = key
            self.name = name
            self.messages = 5

    senders = [FakeSender("1", "Иван"), FakeSender("2", "Пётр")]
    monkeypatch.setattr(gui_api, "list_tg_senders", lambda path: senders)
    api = gui_api.Api(allowed_paths=["path.json"])
    assert api.tg_source("path.json", "unknown") == {
        "error": {"code": "sender_missing", "params": {}}
    }
    found = api.tg_source("path.json", "2")
    assert found["spec"] == "tgexport:path.json#Пётр" and found["label"] == "path.json#Пётр"


def test_open_report_missing_file_is_a_code(tmp_path: Path) -> None:
    api = gui_api.Api()
    missing = tmp_path / "нет.html"
    assert api.open_report(str(missing)) == {"error": {"code": "path_not_allowed", "params": {}}}
    api._written_reports.add(gui_api.norm_path(str(missing)))
    assert api.open_report(str(missing)) == {"error": {"code": "report_missing", "params": {}}}


def test_window_not_ready_raises_chatstyle_error() -> None:
    from chatstyle.errors import ChatstyleError

    with pytest.raises(ChatstyleError):
        gui_api.Api().pick_folder()


def _candidate(label: str, score: float, *, delta: bool, impostors: bool) -> CandidateResult:
    return CandidateResult(
        label=label,
        words=1500,
        messages=300,
        similarity=score / 2,
        delta=DeltaScore(delta, 0.8, 12, ()),
        impostors_score=ImpostorsScore(impostors, score, 4 if impostors else 1, 100),
    )


def test_compare_view_dict_for_impostors_ranking_has_codes_and_short_labels() -> None:
    result = ComparisonResult(
        unknown_label="file:C:/data/unknown.txt",
        unknown=AuthorStats(words=500, messages=90),
        candidates=(
            _candidate("file:C:/data/ivan.txt", 0.9, delta=True, impostors=True),
            _candidate("file:C:/data/petr.txt", 0.3, delta=False, impostors=False),
        ),
        ranked_by=METHOD_IMPOSTORS,
    )
    view = gui_api.compare_view_dict(CompareOutcome(result=result, report_path=None))
    assert view["metric"] == "impostors"
    assert view["candidates"][0]["value"] == 0.9 and view["candidates"][0]["value_text"] == "0.90"
    assert view["candidates"][1]["final"] == "—"
    codes = [note["code"] for note in view["notes"]]
    assert codes[0] == "ranking" and "delta_short" in codes and "impostors_few" in codes
    short = next(note for note in view["notes"] if note["code"] == "delta_short")
    assert short["labels"] == ["petr.txt"] and short["min_chunks"] > 0
    assert view["warning"]["sides"] == [{"who": None, "words": 500}]
    assert view["report_path"] is None


def test_compare_view_dict_clamps_values_to_unit_interval() -> None:
    candidate = CandidateResult(label="a", words=2000, messages=10, similarity=1.7)
    result = ComparisonResult(
        unknown_label="u", unknown=AuthorStats(2000, 10), candidates=(candidate,)
    )
    view = gui_api.compare_view_dict(CompareOutcome(result=result, report_path=None))
    assert view["candidates"][0]["value"] == 1.0
    assert view["warning"] is None
