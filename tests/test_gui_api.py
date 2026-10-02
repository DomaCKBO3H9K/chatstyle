"""Тесты для api.py: методы, которые вызывает веб-интерфейс pywebview."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from chatstyle.errors import ChatstyleError
from chatstyle.gui import api as gui_api


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
    assert resp["errors"]


def test_full_compare(tmp_path: Path) -> None:
    similar = _write_lines(tmp_path / "similar.txt", _similar_lines())
    different = _write_lines(tmp_path / "different.txt", _different_lines())
    unknown = _write_lines(tmp_path / "unknown.txt", _similar_lines())

    api = gui_api.Api()
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
    assert view["summary"]
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
    api = gui_api.Api()
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
    assert second["errors"]


def test_compare_error(tmp_path: Path) -> None:
    unknown = _write_lines(tmp_path / "unknown.txt", _similar_lines())
    api = gui_api.Api()
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
    assert state["message"]


def test_start_profile(tmp_path: Path) -> None:
    author = _write_lines(tmp_path / "author.txt", _similar_lines())
    api = gui_api.Api()
    resp = api.start_profile(f"file:{author}")
    assert resp["ok"] is True
    state = _wait(api)
    assert state["state"] == "done"
    view = state["view"]
    assert view["header"].startswith("Автор:")
    assert len(view["features"]) >= 15
    assert view["word_lines"]


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

    senders = [FakeSender("1", "Иван"), FakeSender("2", "Пётр")]
    monkeypatch.setattr(gui_api, "list_tg_senders", lambda path: senders)
    api = gui_api.Api()
    with pytest.raises(ChatstyleError):
        api.tg_source("path.json", "unknown")
