"""Проверка собранного chatstyle.exe (только Windows): то, что не видно при перенаправлении.

    python packaging/check_exe.py [--exe dist/chatstyle.exe]

Проверяет: свойства файла (версия, описание), иконку, работу при `PATH` без Python, чтение
.env из %APPDATA%\\chatstyle внутри exe (без обращения к сети), вывод в НАСТОЯЩЕЙ консоли (exe
запускается в новой консоли, а экранный буфер читается через Windows API; ширина 80 столбцов),
паузу при запуске «двойным щелчком» (новая консоль, без аргументов) и её отсутствие с аргументами
или с CHATSTYLE_NO_PAUSE=1. Не заменяет проверку на чистой Windows 10 без установленного Python.
"""

import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from chatstyle import __version__

REPO = Path(__file__).resolve().parent.parent
CREATE_NEW_CONSOLE = 0x00000010
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""), flush=True)
    return ok


def clean_env(**extra: str) -> dict[str, str]:
    """Окружение «чистой» машины: только системные каталоги в PATH, без Python."""
    root = os.environ.get("SystemRoot", r"C:\Windows")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "VIRTUAL"))}
    env["PATH"] = rf"{root}\System32;{root}"
    env["CHATSTYLE_HOME"] = str(Path(tempfile.gettempdir()) / "chatstyle_check_home")
    env.update(extra)
    return env


def run_exe(exe: Path, *args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    completed = subprocess.run(
        [str(exe), *args],
        capture_output=True,
        env=env or clean_env(CHATSTYLE_NO_PAUSE="1"),
        cwd=REPO,
        timeout=180,
    )
    return completed.returncode, (completed.stdout + completed.stderr).decode("utf-8", "replace")


# --- чтение и ввод в консоль другого процесса (Windows API) ---


class COORD(ctypes.Structure):
    _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [(n, wintypes.SHORT) for n in ("Left", "Top", "Right", "Bottom")]


class BufferInfo(ctypes.Structure):
    _fields_ = [
        ("dwSize", COORD),
        ("dwCursorPosition", COORD),
        ("wAttributes", wintypes.WORD),
        ("srWindow", SMALL_RECT),
        ("dwMaximumWindowSize", COORD),
    ]


class KeyEvent(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("uChar", wintypes.WCHAR),
        ("dwControlKeyState", wintypes.DWORD),
    ]


class InputRecord(ctypes.Structure):
    class _Event(ctypes.Union):
        _fields_ = [("KeyEvent", KeyEvent)]

    _anonymous_ = ("Event",)
    _fields_ = [("EventType", wintypes.WORD), ("Event", _Event)]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
kernel32.CreateFileW.restype = wintypes.HANDLE


def _open_console(pid: int, device: str) -> wintypes.HANDLE:
    kernel32.FreeConsole()
    if not kernel32.AttachConsole(pid):
        raise OSError(f"AttachConsole({pid}) не удалось: {ctypes.get_last_error()}")
    handle = kernel32.CreateFileW(device, 0xC0000000, 3, None, 3, 0, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise OSError(f"Не удалось открыть {device}")
    return handle


def read_console(pid: int) -> list[str]:
    """Строки экранного буфера консоли процесса `pid` (до строки с курсором включительно)."""
    handle = _open_console(pid, "CONOUT$")
    try:
        info = BufferInfo()
        kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info))
        width = info.dwSize.X
        lines = []
        for row in range(info.dwCursorPosition.Y + 1):
            buffer = ctypes.create_unicode_buffer(width)
            read = wintypes.DWORD(0)
            kernel32.ReadConsoleOutputCharacterW(
                handle, buffer, width, COORD(0, row), ctypes.byref(read)
            )
            lines.append(buffer.value.rstrip())
        return lines
    finally:
        kernel32.CloseHandle(handle)
        kernel32.FreeConsole()


def press_enter(pid: int) -> None:
    """Нажать Enter в консоли процесса `pid` (нажатие и отпускание клавиши)."""
    handle = _open_console(pid, "CONIN$")
    try:
        records = (InputRecord * 2)()
        for index, down in enumerate((True, False)):
            records[index].EventType = 1  # KEY_EVENT
            records[index].KeyEvent = KeyEvent(down, 1, 0x0D, 0x1C, "\r", 0)
        written = wintypes.DWORD(0)
        kernel32.WriteConsoleInputW(handle, records, 2, ctypes.byref(written))
    finally:
        kernel32.CloseHandle(handle)
        kernel32.FreeConsole()


def spawn_in_new_console(command: str, env: dict[str, str]) -> subprocess.Popen[bytes]:
    """Запустить процесс в новой скрытой консоли, как это делает Проводник при двойном щелчке."""
    startup = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    startup.dwFlags |= STARTF_USESHOWWINDOW
    startup.wShowWindow = SW_HIDE
    return subprocess.Popen(  # noqa: S603
        command, env=env, cwd=REPO, creationflags=CREATE_NEW_CONSOLE, startupinfo=startup
    )


def kill_tree(process: subprocess.Popen[bytes]) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)


def wait_for_console_line(process, predicate, timeout: float = 60.0) -> list[str]:  # noqa: ANN001
    """Ждать, пока в буфере консоли появится строка, удовлетворяющая predicate."""
    deadline = time.time() + timeout
    lines: list[str] = []
    while time.time() < deadline:
        time.sleep(1.0)
        try:
            lines = read_console(process.pid)
        except OSError:
            continue
        if any(predicate(line) for line in lines):
            return lines
    return lines


# --- проверки ---


def check_file_properties(exe: Path, label: str = "") -> None:
    command = (
        "Add-Type -AssemblyName System.Drawing;"
        f"$p='{exe}'; $v=(Get-Item -LiteralPath $p).VersionInfo;"
        "$c=[System.Drawing.Icon]::ExtractAssociatedIcon($p).ToBitmap().GetPixel(16,4);"
        "[pscustomobject]@{v=$v.ProductVersion;d=$v.FileDescription;c=$v.CompanyName;"
        "r=$c.R;g=$c.G;b=$c.B} | ConvertTo-Json -Compress"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command], capture_output=True, timeout=120
    ).stdout.decode("utf-8", "replace")
    try:
        info = json.loads(out)
    except json.JSONDecodeError:
        record(f"{label}свойства файла и иконка", False, f"не удалось прочитать: {out!r}")
        return
    record(f"{label}версия в свойствах файла", info["v"] == __version__, f"{info['v']!r}")
    record(f"{label}описание в свойствах файла", "chatstyle" in (info["d"] or ""), repr(info["d"]))
    blue = abs(info["r"] - 42) < 30 and abs(info["g"] - 120) < 30 and abs(info["b"] - 214) < 30
    record(
        f"{label}иконка chatstyle (синий фон)", blue, f"пиксель {info['r']},{info['g']},{info['b']}"
    )


def check_gui_exe(exe: Path) -> None:
    """chatstyle-gui.exe: свойства файла и самопроверка окна.

    Окно скрыто, ввод идёт программно внутри процесса: на рабочий стол и в окна других программ
    ничего не отправляется (никаких синтетических кликов и нажатий клавиш).
    """
    check_file_properties(exe, "GUI: ")
    with tempfile.TemporaryDirectory() as tmp:
        result = Path(tmp) / "selftest.txt"
        process = subprocess.run(
            [str(exe), "--selftest", str(result)],
            env=clean_env(CHATSTYLE_HOME=str(Path(tmp) / "home")),
            cwd=REPO,
            timeout=240,
        )
        text = result.read_text(encoding="utf-8") if result.exists() else ""
        record(
            "GUI: самопроверка внутри exe (сравнение, отчёт, профиль)",
            process.returncode == 0 and text.startswith("OK"),
            text.strip().splitlines()[0]
            if text.strip()
            else f"нет результата, код {process.returncode}",
        )


def check_clean_environment(exe: Path) -> None:
    code, out = run_exe(exe, "--version")
    record(
        "--version без Python в PATH", code == 0 and f"chatstyle {__version__}" in out, out.strip()
    )
    fixtures = "tests/fixtures"
    code, out = run_exe(exe, "features", f"file:{fixtures}/same.txt", "--top", "3")
    record("features (ресурсы внутри exe)", code == 0 and "Частые служебные слова" in out)
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.html"
        args = ["compare", "-u", f"file:{fixtures}/unknown.txt", "-c", f"file:{fixtures}/same.txt"]
        code, out = run_exe(exe, *args, "--report", str(report))
        html = report.read_text(encoding="utf-8") if report.exists() else ""
        record(
            "compare и отчёт .html", code == 0 and "<h1>Отчёт chatstyle</h1>" in html, f"код {code}"
        )


def check_env_file_in_appdata(exe: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "chatstyle"
        folder.mkdir()
        (folder / ".env").write_text("TELEGRAM_API_ID=abc\nTELEGRAM_API_HASH=x\n", encoding="utf-8")
        env = clean_env(CHATSTYLE_NO_PAUSE="1", APPDATA=tmp)
        env.pop("CHATSTYLE_HOME")
        args = ["compare", "-u", "tg:@nobody", "-c", "file:tests/fixtures/same.txt"]
        code, out = run_exe(exe, *args, env=env)
        ok = code == 2 and "должен быть числом" in out
        record(".env читается из %APPDATA%\\chatstyle (без сети)", ok, out.strip()[:120])


def check_real_console(exe: Path) -> None:
    """Таблица в настоящей консоли шириной 80 столбцов."""
    inner = (
        f'mode con: cols=80 lines=300 >nul & "{exe}" compare -u file:tests/fixtures/unknown.txt '
        "-c file:tests/fixtures/same.txt -c file:tests/fixtures/other.txt & echo __DONE__"
    )
    process = spawn_in_new_console(f'cmd.exe /d /s /k "{inner}"', clean_env(CHATSTYLE_HOME=""))
    try:
        lines = wait_for_console_line(process, lambda line: line.strip() == "__DONE__", 90)
    finally:
        kill_tree(process)
    text = "\n".join(lines)
    done = any(line.strip() == "__DONE__" for line in lines)
    record("консоль: команда завершилась", done, f"{len(lines)} строк в буфере")
    header = next((line for line in lines if "Кандидат" in line), "")
    for title in ("Слов", "Сообщений", "Сходство", "Delta", "Impostors (итог)"):
        record(f"консоль 80 столбцов: заголовок «{title}» целиком", title in header)
    record("консоль: рамка таблицы и русский текст", "┌" in text and "Порядок:" in text)
    record("консоль: строки не шире 80", max((len(line) for line in lines), default=0) <= 80)


def check_double_click_pause(exe: Path) -> None:
    quiet = {"PYTHONIOENCODING": "utf-8"}
    process = spawn_in_new_console(f'"{exe}"', clean_env(**quiet))
    try:
        lines = wait_for_console_line(process, lambda line: "Нажмите Enter" in line, 60)
        waiting = any("Нажмите Enter" in line for line in lines) and process.poll() is None
        record(
            "двойной щелчок: справка и ожидание Enter", waiting and "compare" in "\n".join(lines)
        )
        if waiting:
            press_enter(process.pid)
            try:
                process.wait(timeout=30)
                record(
                    "двойной щелчок: после Enter окно закрывается",
                    True,
                    f"код {process.returncode}",
                )
            except subprocess.TimeoutExpired:
                record(
                    "двойной щелчок: после Enter окно закрывается", False, "процесс не завершился"
                )
    finally:
        kill_tree(process)

    for label, command, env in (
        ("с аргументами пауза не нужна", f'"{exe}" --version', clean_env()),
        ("CHATSTYLE_NO_PAUSE=1 отключает паузу", f'"{exe}"', clean_env(CHATSTYLE_NO_PAUSE="1")),
    ):
        process = spawn_in_new_console(command, env)
        try:
            process.wait(timeout=60)
            record(label, True, f"код {process.returncode}")
        except subprocess.TimeoutExpired:
            record(label, False, "процесс ждёт ввода")
        finally:
            kill_tree(process)


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка chatstyle.exe (Windows).")
    parser.add_argument("--exe", type=Path, default=REPO / "dist" / "chatstyle.exe")
    parser.add_argument("--gui-exe", type=Path, default=REPO / "dist" / "chatstyle-gui.exe")
    args = parser.parse_args()
    if sys.platform != "win32":
        print("Проверка выполняется только в Windows.")
        return 2
    exe = args.exe.resolve()
    if not exe.exists():
        print(f"Файл не найден: {exe} (сначала: powershell -File packaging\\build_exe.ps1)")
        return 2
    print(f"Проверяется {exe} ({exe.stat().st_size / 1e6:.1f} МБ)")
    check_file_properties(exe)
    check_clean_environment(exe)
    check_env_file_in_appdata(exe)
    check_real_console(exe)
    check_double_click_pause(exe)
    gui_exe = args.gui_exe.resolve()
    if gui_exe.exists():
        print(f"Проверяется {gui_exe} ({gui_exe.stat().st_size / 1e6:.1f} МБ)")
        check_gui_exe(gui_exe)
    else:
        hint = "powershell -File packaging\\build_exe.ps1 -Target gui"
        print(f"Пропущено: {gui_exe} не найден ({hint})")
    failed = [name for name, ok, _ in results if not ok]
    print(f"\nИтого: {len(results) - len(failed)} из {len(results)} проверок пройдено.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
