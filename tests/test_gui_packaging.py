import runpy
import sys
import tomllib
from pathlib import Path

import pytest
from chatstyle.gui import selftest

REPO = Path(__file__).resolve().parent.parent
PACKAGING = REPO / "packaging"


# --- самопроверка окна ---


def test_selftest_passes_and_writes_ok(tmp_path: Path) -> None:
    result = tmp_path / "result.txt"
    code = selftest.run(result)
    text = result.read_text(encoding="utf-8")
    if code != 0 and "WebView2" in text:
        pytest.skip("нет WebView2 для окна")
    assert code == 0, text
    assert text.startswith("OK: сравнение 2 кандидатов, отчёт, профиль, языки, тема")


def test_selftest_failure_is_written_with_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> str:
        raise AssertionError("сломано")

    monkeypatch.setattr(selftest, "check", broken)
    result = tmp_path / "result.txt"
    assert selftest.run(result) == 1
    text = result.read_text(encoding="utf-8")
    assert text.startswith("FAIL:") and "AssertionError: сломано" in text


def test_gui_entry_point_dispatches_selftest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(selftest, "run", lambda path: calls.append(path) or 0)
    monkeypatch.setattr(sys, "argv", ["chatstyle-gui", "--selftest", str(tmp_path / "r.txt")])
    entry = runpy.run_path(str(REPO / "python" / "chatstyle" / "gui" / "__main__.py"))
    with pytest.raises(SystemExit) as exc_info:
        entry["main"]()
    assert exc_info.value.code == 0 and calls == [tmp_path / "r.txt"]


def test_gui_entry_point_survives_missing_standard_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # сборка без консоли (console=False): sys.stdout и sys.stderr равны None
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr("chatstyle.gui.main", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["chatstyle-gui"])
    entry = runpy.run_path(str(REPO / "python" / "chatstyle" / "gui" / "__main__.py"))
    with pytest.raises(SystemExit) as exc_info:
        entry["main"]()
    assert exc_info.value.code == 0
    assert sys.stdout is not None and sys.stderr is not None  # print() больше не упадёт


# --- файлы сборки ---


def test_pyproject_declares_the_gui_launcher() -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["gui-scripts"] == {"chatstyle-gui": "chatstyle.gui:main"}
    assert any(item.startswith("pywebview") for item in project["dependencies"])
    assert project["scripts"]["chatstyle"] == "chatstyle.cli:app"


def test_gui_spec_is_windowed_and_ships_the_web_page() -> None:
    spec = (PACKAGING / "chatstyle_gui.spec").read_text(encoding="utf-8")
    assert "console=False" in spec
    assert 'name="chatstyle-gui"' in spec
    hidden = spec.split("hiddenimports=")[1].split("]")[0]
    assert '"webview"' in hidden and '"webview.platforms.edgechromium"' in hidden
    excludes = spec.split("EXCLUDES = [")[1].split("]")[0]
    assert '"tkinter"' in excludes  # окно рисует WebView2
    for module in ("IPython", "numpy", "matplotlib", "pandas"):
        assert f'"{module}"' in excludes
    assert '"chatstyle/gui/web"' in spec  # страница интерфейса едет в exe как ресурс
    assert "CHATSTYLE_ONEDIR" in spec and "chatstyle.ico" in spec and "version_info.txt" in spec


def test_build_script_builds_both_exes_and_stays_ascii() -> None:
    raw = (PACKAGING / "build_exe.ps1").read_bytes()
    raw.decode("ascii")  # Windows PowerShell 5.1 читает файл без BOM как ANSI
    for fragment in (
        b"ValidateSet('cli', 'gui', 'all')",
        b"[switch]$OneDir",
        b"chatstyle_gui.spec",
    ):
        assert fragment in raw
    assert b"-Target cli" in raw and b"-Target gui" in raw


def test_window_icon_is_a_package_resource() -> None:
    from importlib import resources

    icon = resources.files("chatstyle").joinpath("resources", "chatstyle.ico")
    assert icon.is_file()


# --- страница интерфейса ---


def _web_file(name: str) -> str:
    from importlib import resources

    return resources.files("chatstyle").joinpath("gui", "web", name).read_text(encoding="utf-8")


def test_web_page_is_self_contained() -> None:
    page = _web_file("index.html")
    assert "default-src 'self'" in page  # страница не может тянуть ничего снаружи
    names = ["index.html", "style.css", "app.js", "i18n.js"]
    names += [f"lang/{code}.js" for code in ("ru", "en", "ar", "es", "zh", "fr")]
    for name in names:
        text = _web_file(name)
        assert "http://" not in text.replace("http://www.w3.org", "")
        assert "https://" not in text
    assert 'href="style.css"' in page and 'src="app.js"' in page


def test_web_script_never_inserts_markup_from_data() -> None:
    for name in ("app.js", "i18n.js"):
        script = _web_file(name)
        for dangerous in (
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
        ):
            assert dangerous not in script, (name, dangerous)  # чужие имена — только как текст


def test_dark_theme_defines_every_color_token_of_the_light_theme() -> None:
    import re

    css = _web_file("style.css")
    light = css.split(":root {")[1].split("}")[0]
    dark = css.split(':root[data-theme="dark"] {')[1].split("}")[0]
    system_dark = css.split("@media (prefers-color-scheme: dark)")[1].split("}")[0]

    def colors(block: str) -> set[str]:
        return set(re.findall(r"(--[a-z0-9-]+):\s*(?:#|rgba)", block))

    assert colors(light) and colors(light) == colors(dark) == colors(system_dark)
    assert 'id="theme"' in _web_file("index.html")
