"""Снимки настоящего окна на вымышленных данных docs/demo/ для README (только Windows).

    python tools/make_screenshots.py ЯЗЫК ПАПКА     # один язык, отдельный процесс
    python tools/make_screenshots.py all ПАПКА      # все шесть языков по очереди

Окно открывается на экране на несколько секунд: снимается область экрана, поэтому другие окна
не должны его перекрывать (окно ставится поверх остальных). Своих данных скрипт не трогает:
папка данных и хранилище временные, чаты лежат только в памяти.
"""

import ctypes
import faulthandler
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LANGUAGES = ("ru", "en", "es", "fr", "zh", "ar")
SIZE = (1180, 820)


def load_export_module():  # noqa: ANN201
    spec = importlib.util.spec_from_file_location(
        "make_demo_export", REPO / "docs" / "make_demo_export.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_demo_export"] = module
    spec.loader.exec_module(module)
    return module


def window_rect(window) -> tuple[int, int, int, int]:  # noqa: ANN001
    from ctypes import wintypes

    handle = int(window.native.Handle.ToInt64())
    rect = wintypes.RECT()
    # DWMWA_EXTENDED_FRAME_BOUNDS (9): видимая рамка без невидимой тени вокруг окна
    done = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(handle), 9, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    if done != 0:
        ctypes.windll.user32.GetWindowRect(wintypes.HWND(handle), ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def keep_on_top(window) -> None:  # noqa: ANN001
    """Поставить окно поверх остальных (window.on_top из рабочего потока зависает)."""
    from ctypes import wintypes

    handle = wintypes.HWND(int(window.native.Handle.ToInt64()))
    # HWND_TOPMOST = -1; SWP_NOSIZE | SWP_NOMOVE = 3
    ctypes.windll.user32.SetWindowPos(handle, wintypes.HWND(-1), 0, 0, 0, 0, 3)


def snap(window, target: Path) -> None:  # noqa: ANN001
    from PIL import ImageGrab

    time.sleep(1.2)  # страница дорисовывает шкалы и подсветку
    left, top, right, bottom = window_rect(window)
    ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).save(target, optimize=True)


def js(window, code: str):  # noqa: ANN001, ANN201
    return window.evaluate_js(code)


def scenario(window, lang: str, out: Path, folder: Path) -> None:  # noqa: ANN001
    from chatstyle import chatstore
    from chatstyle.gui.selftest import _setup_chat_protection, _wait

    export = load_export_module()
    paths = export.write_all(folder, (lang,))
    people = export.people_of(lang)
    titles = export.titles(lang)

    _wait(
        window,
        "typeof window.pywebview !== 'undefined' && !!document.getElementById('go')"
        " && document.getElementById('disclaimer').textContent.length > 0",
        30.0,
        "загрузка страницы",
    )
    keep_on_top(window)
    js(
        window,
        f"(document.getElementById('lang').value = '{lang}',"
        " document.getElementById('lang').dispatchEvent(new Event('change')), true)",
    )
    if js(window, "currentTheme()") != "light":
        js(window, "document.getElementById('theme').click()")

    _setup_chat_protection(window)
    for path in paths:
        chatstore.import_chat(path)
    chat_ids = {chat: export.CHATS[chat][0] for chat in export.CHATS}

    def source(chat: str, name: str) -> str:
        spec = f"chat:{chat_ids[chat]}#{name}"
        return json.dumps({"spec": spec, "label": f"{name} · {titles[chat]}"}, ensure_ascii=False)

    candidates = ", ".join(source("trip", name) for name in people)
    js(
        window,
        f"(state.unknown = {source('work', people[0])},"
        f" state.candidates.push({candidates}), refreshCompare(),"
        " document.getElementById('go').click(), true)",
    )
    _wait(
        window, f"document.querySelectorAll('.cand').length === {len(people)}", 120.0, "результат"
    )
    js(window, "document.getElementById('tab-compare').click()")
    snap(window, out / f"compare-{lang}.png")

    # профиль строится по файлу: в диалоге окна путь выбирает человек, здесь его «выбираем» сами
    vera = [
        text
        for name, text in (
            line.split(chr(9), 1)
            for line in (REPO / "docs" / "demo" / f"trip.{lang}.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        if name == people[2]
    ]
    vera_file = folder / f"{people[2]}.txt"
    vera_file.write_text(chr(10).join(vera), encoding="utf-8")
    window._chatstyle_api._remember_path(str(vera_file))
    profile_source = json.dumps(
        {"spec": f"file:{vera_file}", "label": f"{people[2]} · {titles['trip']}"},
        ensure_ascii=False,
    )
    js(
        window,
        f"(state.profile = {profile_source}, refreshCompare(),"
        " document.getElementById('tab-profile').click(),"
        " document.getElementById('go-profile').click(), true)",
    )
    try:
        _wait(window, "document.querySelectorAll('.feature').length >= 10", 60.0, "профиль")
    except TimeoutError:
        shown = js(
            window,
            "[document.getElementById('error').textContent,"
            " document.querySelectorAll('.feature').length,"
            " document.getElementById('go-profile').disabled, JSON.stringify(state.profile)]",
        )
        raise TimeoutError(f"профиль не построился: {shown}") from None
    snap(window, out / f"profile-{lang}.png")

    js(window, "document.getElementById('tab-chats').click()")
    _wait(window, "document.querySelectorAll('#chats-list li').length === 2", 30.0, "список чатов")
    snap(window, out / f"chats-{lang}.png")


def run_one(lang: str, out: Path) -> None:
    faulthandler.dump_traceback_later(240, exit=True)  # зависание не должно длиться вечно
    import webview
    from chatstyle.gui.app import create_window
    from chatstyle.securestore import Vault, reset_default_vault

    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    out.mkdir(parents=True, exist_ok=True)
    home = tempfile.TemporaryDirectory()
    os.environ["CHATSTYLE_HOME"] = home.name
    failure: list[str] = []

    def work(window) -> None:  # noqa: ANN001
        try:
            with tempfile.TemporaryDirectory() as tmp:
                reset_default_vault(Vault(Path(tmp) / "vault.json", backoff=False))
                scenario(window, lang, out, Path(tmp))
        except BaseException:  # noqa: BLE001
            failure.append(traceback.format_exc())
        finally:
            reset_default_vault(None)
            window.destroy()

    window = create_window(hidden=False)
    watchdog = threading.Timer(300.0, window.destroy)
    watchdog.daemon = True
    watchdog.start()
    try:
        webview.start(work, window, gui="edgechromium")
    finally:
        watchdog.cancel()
        home.cleanup()
    if failure:
        raise SystemExit(failure[0])


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        raise SystemExit(__doc__)
    lang, out = argv[1], Path(argv[2])
    if lang != "all":
        run_one(lang, out)
        return
    for code in LANGUAGES:
        print(code, flush=True)
        done = subprocess.run([sys.executable, __file__, code, str(out)], check=False)
        if done.returncode != 0:
            raise SystemExit(f"{code}: код выхода {done.returncode}")


if __name__ == "__main__":
    main(sys.argv)
