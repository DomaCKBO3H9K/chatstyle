"""Запуск CLI: пауза перед закрытием окна, если exe запущен двойным щелчком (Windows).

Двойной щелчок по chatstyle.exe открывает консоль только для него, и окно закрывается сразу
после завершения программы: справку или сообщение об ошибке не успеть прочитать. Поэтому в
такой ситуации программа ждёт Enter. Из cmd, PowerShell или Windows Terminal пауза не нужна и
не включается.
"""

import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

NO_PAUSE_VAR = "CHATSTYLE_NO_PAUSE"
PAUSE_MESSAGE = "Нажмите Enter, чтобы закрыть окно..."

# В режиме --onefile PyInstaller держит два процесса (загрузчик и сам chatstyle), оба на одной
# консоли. Если на консоли только они, консоль создана для нашего exe, то есть двойной щелчок.
_ONEFILE_PROCESSES = 2
_MAX_LISTED = 64


def console_process_count() -> int | None:
    """Сколько процессов делят консоль (только Windows); None, если консоли нет или не Windows."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        buffer = (ctypes.c_uint * _MAX_LISTED)()
        count = int(ctypes.windll.kernel32.GetConsoleProcessList(buffer, _MAX_LISTED))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return None
    return count or None  # 0 — консоли нет (или вызов не удался)


def should_pause(
    argv: Sequence[str],
    *,
    frozen: bool,
    process_count: int | None,
    environ: Mapping[str, str],
) -> bool:
    """Нужна ли пауза: exe запущен двойным щелчком (консоль своя, аргументов нет)."""
    if environ.get(NO_PAUSE_VAR):
        return False
    if not frozen or len(argv) > 1 or process_count is None:
        return False
    return process_count <= _ONEFILE_PROCESSES


def pause() -> None:
    """Подождать Enter; если ввод недоступен, просто вернуться."""
    print(f"\n{PAUSE_MESSAGE}", flush=True)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def configure_streams(streams: Sequence[TextIO] | None = None) -> None:
    """Вывод без терминала (перенаправление в файл или канал) всегда в UTF-8.

    Иначе кодировка зависит от системы и способа запуска: в exe PyInstaller игнорирует
    PYTHONIOENCODING и берёт кодовую страницу консоли (например, cp866), и русский текст в
    файле получается нечитаемым для остальных программ. В терминале ничего не меняется:
    Python сам пишет в консоль Windows через Unicode API.
    """
    for stream in streams if streams is not None else (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None and not stream.isatty():
            reconfigure(encoding="utf-8", errors="replace")
