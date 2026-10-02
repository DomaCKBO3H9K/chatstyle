import runpy
import struct
import sys
import tomllib
from pathlib import Path

import pytest
from chatstyle import __main__ as entry
from chatstyle import __version__, _core, launcher
from chatstyle.cli import app
from typer.testing import CliRunner

REPO = Path(__file__).resolve().parent.parent
PACKAGING = REPO / "packaging"
ICON = REPO / "python" / "chatstyle" / "resources" / "chatstyle.ico"


def load_script(name: str) -> dict:
    """Скрипт из packaging/ (имя папки совпадает с PyPI-пакетом packaging, поэтому runpy)."""
    return runpy.run_path(str(PACKAGING / name), run_name=f"packaging_{name}")


# --- когда нужна пауза ---


@pytest.mark.parametrize(
    ("argv", "frozen", "count", "env", "expected"),
    [
        (["chatstyle.exe"], True, 2, {}, True),  # двойной щелчок: консоль только наша
        (["chatstyle.exe"], True, 1, {}, True),
        (["chatstyle.exe"], True, 3, {}, False),  # запущен из cmd/PowerShell: есть оболочка
        (["chatstyle.exe", "--version"], True, 2, {}, False),  # с аргументами
        (["chatstyle.exe"], False, 2, {}, False),  # обычный Python, не exe
        (["chatstyle.exe"], True, None, {}, False),  # консоли нет или не Windows
        (["chatstyle.exe"], True, 2, {"CHATSTYLE_NO_PAUSE": "1"}, False),  # явное отключение
    ],
)
def test_should_pause(
    argv: list[str], frozen: bool, count: int | None, env: dict[str, str], expected: bool
) -> None:
    assert launcher.should_pause(argv, frozen=frozen, process_count=count, environ=env) is expected


def test_pause_prints_message_and_waits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr("builtins.input", lambda: calls.append("input") or "")
    launcher.pause()
    assert launcher.PAUSE_MESSAGE in capsys.readouterr().out
    assert calls == ["input"]


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_pause_survives_missing_input(monkeypatch: pytest.MonkeyPatch, error: type) -> None:
    def fail() -> str:
        raise error

    monkeypatch.setattr("builtins.input", fail)
    launcher.pause()  # не бросает исключение


def test_console_process_count_is_none_outside_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert launcher.console_process_count() is None


def test_console_process_count_is_a_positive_number_or_none() -> None:
    count = launcher.console_process_count()
    assert count is None or count >= 1


# --- сохранение кода выхода и пауза в main() ---


@pytest.mark.parametrize(
    ("argv", "code"),
    [(["chatstyle", "--version"], 0), (["chatstyle", "compare"], 2)],
)
def test_main_pauses_after_the_command_and_keeps_the_exit_code(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], code: int
) -> None:
    paused: list[bool] = []
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(launcher, "should_pause", lambda *a, **k: True)
    monkeypatch.setattr(launcher, "pause", lambda: paused.append(True))
    monkeypatch.setattr(launcher, "configure_streams", lambda *a, **k: None)
    with pytest.raises(SystemExit) as exc_info:
        entry.main()
    assert exc_info.value.code == code
    assert paused == [True]  # пауза и при успехе, и при ошибке


def test_main_does_not_pause_when_not_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    paused: list[bool] = []
    monkeypatch.setattr(sys, "argv", ["chatstyle", "--version"])
    monkeypatch.setattr(launcher, "should_pause", lambda *a, **k: False)
    monkeypatch.setattr(launcher, "pause", lambda: paused.append(True))
    with pytest.raises(SystemExit):
        entry.main()
    assert paused == []


# --- вывод без терминала в UTF-8 ---


class FakeStream:
    def __init__(self, tty: bool) -> None:
        self.tty = tty
        self.reconfigured: list[dict[str, str]] = []

    def isatty(self) -> bool:
        return self.tty

    def reconfigure(self, **kwargs: str) -> None:
        self.reconfigured.append(kwargs)


class NoReconfigure:
    def isatty(self) -> bool:
        return False


def test_streams_without_terminal_become_utf8() -> None:
    piped, terminal = FakeStream(False), FakeStream(True)
    launcher.configure_streams([piped, terminal, NoReconfigure()])  # type: ignore[list-item]
    assert piped.reconfigured == [{"encoding": "utf-8", "errors": "replace"}]
    assert terminal.reconfigured == []  # терминал не трогаем


# --- версия: один источник ---


def test_version_is_the_same_in_package_core_and_pyproject() -> None:
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__ == _core.version()


def test_version_resource_is_generated_from_the_package_version() -> None:
    script = load_script("make_version_info.py")
    text = script["render"]()
    assert f"filevers={tuple(int(p) for p in __version__.split('.')) + (0,)}" in text
    assert f"StringStruct('ProductVersion', '{__version__}')" in text
    assert "StringStruct('OriginalFilename', 'chatstyle.exe')" in text
    assert "VarStruct('Translation', [1049, 1200])" in text
    assert script["version_tuple"]("1.2.3") == (1, 2, 3, 0)
    with pytest.raises(ValueError):
        script["version_tuple"]("1.2")


def test_version_resource_is_valid_for_pyinstaller(tmp_path: Path) -> None:
    pytest.importorskip("PyInstaller")
    from PyInstaller.utils.win32.versioninfo import VSVersionInfo  # noqa: F401

    namespace = {}
    exec(  # noqa: S102
        "from PyInstaller.utils.win32.versioninfo import *\n"
        + load_script("make_version_info.py")["render"](),
        namespace,
    )
    assert namespace["VSVersionInfo"] is not None


# --- иконка и файлы сборки ---


def parse_ico(data: bytes) -> list[tuple[int, int, bytes]]:
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, kind) == (0, 1)
    frames = []
    for index in range(count):
        width, height, _, _, planes, bits, size, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * index
        )
        frames.append((width or 256, height or 256, data[offset : offset + size]))
        assert (planes, bits) == (1, 32)
    return frames


def test_committed_icon_is_a_valid_multi_size_ico() -> None:
    frames = parse_ico(ICON.read_bytes())
    assert [w for w, _, _ in frames] == [16, 24, 32, 48, 64, 128, 256]
    for width, height, png in frames:
        assert width == height
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", png[16:24]) == (width, height)  # размеры в заголовке PNG


def test_icon_generator_reproduces_the_frames(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    script = load_script("make_icon.py")
    target = tmp_path / "icon.ico"
    script["main"](target)
    generated = parse_ico(target.read_bytes())
    committed = parse_ico(ICON.read_bytes())
    assert [(w, h) for w, h, _ in generated] == [(w, h) for w, h, _ in committed]


def test_build_script_is_ascii_only_for_windows_powershell() -> None:
    # Windows PowerShell 5.1 читает файл без BOM как ANSI: кириллица ломает разбор строк
    raw = (PACKAGING / "build_exe.ps1").read_bytes()
    assert raw.decode("ascii")  # не бросает исключение
    assert b"[switch]$OneDir" in raw


def test_spec_supports_onedir_and_excludes_heavy_modules() -> None:
    spec = (PACKAGING / "chatstyle.spec").read_text(encoding="utf-8")
    assert "CHATSTYLE_ONEDIR" in spec and "COLLECT(" in spec
    for module in ("IPython", "numpy", "matplotlib", "pandas"):
        assert f'"{module}"' in spec  # иначе rich.pretty втянет окружение разработчика (96 МБ)
    assert "chatstyle.ico" in spec and "version_info.txt" in spec


# --- узкий терминал ---


def test_table_headers_stay_whole_at_80_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO)
    result = CliRunner().invoke(
        app,
        ["compare", "-u", "file:tests/fixtures/unknown.txt"]
        + ["-c", "file:tests/fixtures/same.txt", "-c", "file:tests/fixtures/other.txt"],
        env={"COLUMNS": "80"},
    )
    assert result.exit_code == 0
    header = next(line for line in result.output.splitlines() if "Кандидат" in line)
    for title in ("Слов", "Сообщений", "Сходство", "Delta", "Impostors (итог)"):
        assert title in header
