"""Жёсткие параметры окна: белые списки путей, проверка входных данных, настройки, порты."""

import json
import subprocess
import sys
import time
from importlib import resources
from pathlib import Path

import pytest
from chatstyle.gui import api as gui_api
from chatstyle.gui import app as gui_app
from chatstyle.gui import selftest
from chatstyle.gui import settings as gui_settings

REPO = Path(__file__).resolve().parent.parent


def _web(name: str) -> str:
    return Path(str(resources.files("chatstyle").joinpath("gui", "web", name))).read_text(
        encoding="utf-8"
    )


class SpyLogin:
    """Подмена TelegramLogin: любое обращение считается нарушением."""

    def touch(self) -> None:  # продление замка допустимо: это не вход и не сеть
        return None

    def __getattr__(self, name: str):  # noqa: ANN204
        raise AssertionError(f"к входу в Telegram не должно быть обращений: {name}")


def _api(**kwargs: object) -> gui_api.Api:
    return gui_api.Api(telegram=SpyLogin(), **kwargs)  # type: ignore[arg-type]


def _form(**changes: object) -> dict:
    form = {
        "unknown": "file:u.txt",
        "candidates": ["file:a.txt"],
        "impostors_dir": "",
        "seed": "1",
        "report_path": "",
    }
    return {**form, **changes}


def _codes(answer: dict) -> list[str]:
    return [item["code"] for item in answer["errors"]]


# --- пути только из диалогов этого окна ---


def test_paths_not_chosen_in_a_dialog_are_refused() -> None:
    api = _api()
    assert _codes(api.start_compare(_form())) == ["path_not_allowed"]
    assert _codes(api.start_compare(_form(unknown="tgexport:x.json#Анна"))) == ["path_not_allowed"]
    assert _codes(api.start_profile("file:u.txt")) == ["path_not_allowed"]
    assert _codes(api.start_profile("u.txt")) == ["path_not_allowed"]  # голый путь тоже


def test_only_known_schemes_are_accepted() -> None:
    api = _api(allowed_paths=["u.txt"])
    for bad in ("http://evil/x", "ftp:x", "javascript:alert(1)", "x:y", "file:", "tg:  "):
        assert _codes(api.start_compare(_form(unknown=bad, candidates=[]))) == ["path_not_allowed"]


def test_telegram_sources_need_no_file_but_other_paths_are_checked(tmp_path: Path) -> None:
    api = _api(allowed_paths=["a.txt"])
    ok = api.start_compare(_form(unknown="tg:@stranger#@human", candidates=["file:a.txt"]))
    assert ok.get("ok") is True or "errors" not in ok  # дошло до запуска
    api2 = _api()
    folder = str(tmp_path)
    assert _codes(
        api2.start_compare(_form(unknown="tg:@x", candidates=["tg:@y"], impostors_dir=folder))
    ) == ["path_not_allowed"]
    assert _codes(
        api2.start_compare(_form(unknown="tg:@x", candidates=["tg:@y"], report_path="r.html"))
    ) == ["path_not_allowed"]


def test_dialog_choices_open_the_whitelist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chosen = {"value": str(tmp_path / "a.txt")}

    class Window:
        def create_file_dialog(self, kind, **kwargs):  # noqa: ANN001, ANN201
            return (chosen["value"],)

    api = gui_api.Api(lambda: Window(), telegram=SpyLogin())  # type: ignore[arg-type]
    picked = api.pick_file()
    assert picked is not None and picked["spec"] == f"file:{chosen['value']}"
    assert api._spec_allowed(picked["spec"])
    assert not api._spec_allowed("file:" + str(tmp_path / "other.txt"))
    folder = api.pick_folder()
    assert folder is not None and gui_api.norm_path(folder) in api._allowed_paths
    report = api.pick_report_path()
    assert report is not None and gui_api.norm_path(report) in api._allowed_reports


def test_path_comparison_ignores_case_and_relative_forms(tmp_path: Path) -> None:
    api = _api(allowed_paths=[str(tmp_path / "A.txt")])
    assert api._spec_allowed(f"file:{str(tmp_path / 'a.txt').upper()}") == (sys.platform == "win32")
    assert not api._spec_allowed(f"file:{tmp_path}/sub/../../A.txt")


def test_tg_source_reads_only_a_chosen_export() -> None:
    answer = _api().tg_source("some.json", "1")
    assert answer == {"error": {"code": "path_not_allowed", "params": {}}}


# --- форма и любые данные со страницы проверяются ---


@pytest.mark.parametrize(
    "form",
    [
        None,
        "строка",
        [],
        _form(candidates="file:a.txt"),
        _form(candidates=[1]),
        _form(candidates=["file:a.txt"] * 51),
        _form(unknown="x" * 5000),
        _form(unknown="file:\x00a.txt"),
        _form(seed=1),
        _form(limit=5),
        _form(refresh="yes"),
        _form(impostors_dir=None),
    ],
)
def test_malformed_forms_are_rejected_before_anything_runs(form: object) -> None:
    answer = _api(allowed_paths=["u.txt", "a.txt"]).start_compare(form)  # type: ignore[arg-type]
    assert answer["ok"] is False and _codes(answer) == ["bad_input"]


def test_profile_source_must_be_text() -> None:
    api = _api()
    assert _codes(api.start_profile(5)) == ["bad_input"]  # type: ignore[arg-type]
    assert _codes(api.start_profile("x" * 5000)) == ["bad_input"]


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("telegram_begin", (5,)),
        ("telegram_begin", ("1" * 65,)),
        ("telegram_code", ("1" * 33,)),
        ("telegram_code", (None,)),
        ("telegram_password", ("x" * 257,)),
        ("telegram_password", (b"x",)),
        ("telegram_save_keys", ("1" * 21, "a" * 32)),
        ("telegram_save_keys", ("1", "a" * 65)),
        ("telegram_save_keys", (1, "a" * 32)),
    ],
)
def test_telegram_arguments_are_checked_without_touching_the_login(
    method: str, args: tuple
) -> None:
    answer = getattr(_api(), method)(*args)
    assert answer == {"ok": False, "error": {"code": "bad_input", "params": {}}}


def test_tg_source_arguments_must_be_text() -> None:
    assert _api().tg_source(5, "k") == {"error": {"code": "bad_input", "params": {}}}  # type: ignore[arg-type]


# --- отчёт открывается только созданный этим окном ---


def test_only_reports_written_by_this_window_can_be_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(gui_api.os, "startfile", lambda path: opened.append(path), raising=False)
    monkeypatch.setattr(gui_api.sys, "platform", "win32")
    other = tmp_path / "secret.txt"
    other.write_text("x", encoding="utf-8")
    report = tmp_path / "r.html"
    report.write_text("<p>x</p>", encoding="utf-8")
    api = _api()
    assert api.open_report(str(other))["error"]["code"] == "path_not_allowed"
    assert api.open_report(str(report))["error"]["code"] == "path_not_allowed"
    api._written_reports.add(gui_api.norm_path(str(other)))
    assert (
        api.open_report(str(other))["error"]["code"] == "path_not_allowed"
    )  # расширение не отчёта
    api._written_reports.add(gui_api.norm_path(str(report)))
    assert api.open_report(str(report)) is None and opened == [str(report)]


def test_a_finished_comparison_registers_its_report(tmp_path: Path) -> None:
    lines = [
        f"Сегодня я хочу рассказать о том, как проверяется стиль автора {i}" for i in range(60)
    ]
    files = []
    for name in ("u.txt", "a.txt"):
        path = tmp_path / name
        path.write_text("\n".join(lines), encoding="utf-8")
        files.append(str(path))
    report = tmp_path / "report.html"
    api = _api(allowed_paths=files, allowed_reports=[str(report)])
    form = _form(
        unknown=f"file:{files[0]}", candidates=[f"file:{files[1]}"], report_path=str(report)
    )
    assert api.start_compare(form)["ok"] is True
    deadline = time.time() + 60
    state: dict = {}
    while time.time() < deadline:
        state = api.poll()
        if state["state"] != "running":
            break
        time.sleep(0.05)
    assert state["state"] == "done" and state["view"]["report_path"] == str(report)
    assert gui_api.norm_path(str(report)) in api._written_reports


# --- настройки ---


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CHATSTYLE_HOME", str(tmp_path))
    return tmp_path


def test_settings_roundtrip_and_whitelist(home: Path) -> None:
    api = _api()
    assert api.get_settings() == {}
    assert api.set_setting("language", "ar")["settings"] == {"language": "ar"}
    assert api.set_setting("theme", "dark")["settings"] == {"language": "ar", "theme": "dark"}
    assert api.get_settings() == {"language": "ar", "theme": "dark"}
    assert not list(home.glob("*.tmp"))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("language", "de"),
        ("theme", "red"),
        ("shell", "dark"),
        ("language", 5),
        (5, "ru"),
        ("theme", None),
    ],
)
def test_settings_refuse_anything_outside_the_whitelist(
    home: Path, name: object, value: object
) -> None:
    answer = _api().set_setting(name, value)  # type: ignore[arg-type]
    assert answer["ok"] is False and answer["error"]["code"] == "core"
    assert not (home / gui_settings.FILE_NAME).exists()


def test_a_tampered_settings_file_is_filtered(home: Path) -> None:
    (home / gui_settings.FILE_NAME).write_text(
        json.dumps({"language": "ru", "theme": "<script>", "evil": "x", "extra": [1]}),
        encoding="utf-8",
    )
    assert gui_settings.load_settings() == {"language": "ru"}
    (home / gui_settings.FILE_NAME).write_text("не json", encoding="utf-8")
    assert gui_settings.load_settings() == {}
    (home / gui_settings.FILE_NAME).write_text("[1, 2]", encoding="utf-8")
    assert gui_settings.load_settings() == {}


def test_settings_languages_match_the_ones_the_page_knows() -> None:
    import re

    declared = re.findall(r'\{ code: "(\w+)"', _web("i18n.js"))
    assert tuple(declared) == gui_settings.ALLOWED["language"]


# --- страница: без локального сервера, браузерного хранилища и лишнего ---


def test_window_is_loaded_from_a_file_url_not_a_local_server() -> None:
    url = gui_app.index_url()
    assert url.startswith("file:///") and url.endswith("/gui/web/index.html")


def test_page_never_uses_browser_storage_or_the_network() -> None:
    for name in ("app.js", "i18n.js"):
        script = _web(name)
        for banned in (
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
        ):
            assert banned not in script, (name, banned)
        for banned in ("document.cookie", "window.open", "location.href", "location.assign"):
            assert banned not in script, (name, banned)


def test_path_fields_cannot_be_typed_into() -> None:
    page = _web("index.html")
    assert 'id="impostors" readonly' in page and 'id="report" readonly' in page


def test_secret_fields_are_not_autofilled() -> None:
    script = _web("app.js")
    assert 'autocomplete: "off"' in script and 'type: "password"' in script


def test_window_installs_a_navigation_guard_and_blocks_external_links() -> None:
    source = (REPO / "python" / "chatstyle" / "gui" / "app.py").read_text(encoding="utf-8")
    assert "NavigationStarting" in source and "args.Cancel = True" in source
    assert 'OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False' in source
    assert "private_mode=True" in source and "private_mode=False" not in source


# --- проверка самопроверки: она действительно видит слушающий порт ---


@pytest.mark.skipif(sys.platform != "win32", reason="netstat и CIM есть только в Windows")
def test_the_listening_socket_check_sees_a_real_listener() -> None:
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", "0", "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 15
        found: list[str] = []
        while time.time() < deadline and not found:
            time.sleep(0.5)
            found = selftest._listening_sockets()
        assert found and "127.0.0.1" in found[0]
    finally:
        server.kill()
        server.wait()
