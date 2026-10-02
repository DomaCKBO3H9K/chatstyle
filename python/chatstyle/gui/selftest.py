"""Самопроверка окна без участия пользователя: `chatstyle-gui.exe --selftest ФАЙЛ`.

Окно создаётся скрытым и работает как настоящее: страница `gui/web` загружается в WebView2, форма
заполняется состоянием страницы, кнопки нажимаются внутри страницы (DOM), расчёт проходит весь
путь JavaScript -> Api -> ядро -> JavaScript. Ничего не отправляется ни в окна других программ,
ни на рабочий стол. Результат (`OK ...` или текст ошибки) записывается в ФАЙЛ: у сборки без
консоли нет stdout. Нужна, чтобы проверить собранный exe (WebView2, ресурсы, потоки, ядро)
без ручных кликов.
"""

import json
import random
import tempfile
import threading
import time
import traceback
from pathlib import Path

_CASUAL = ["ну", "типа", "короче", "блин", "я", "и", "не", "щас"]
_FORMAL = ["что", "для", "при", "также", "однако", "это", "в", "поэтому"]
PAGE_TIMEOUT = 40.0
JOB_TIMEOUT = 90.0


def _lines(words: list[str], seed: int, formal: bool, count: int = 60) -> list[str]:
    rng = random.Random(seed)
    lines = []
    for _ in range(count):
        text = " ".join(rng.choice(words) for _ in range(rng.randint(8, 12)))
        lines.append(text.capitalize() + "." if formal else text + "))")
    return lines


def _write(path: Path, lines: list[str]) -> str:
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _wait(window, expression: str, timeout: float, what: str) -> None:  # noqa: ANN001
    """Ждать, пока выражение JavaScript в странице станет истинным."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if window.evaluate_js(expression):
                return
        except Exception:  # noqa: BLE001, S110 - страница ещё грузится, пробуем снова
            pass
        time.sleep(0.15)
    raise TimeoutError(f"не дождались: {what}")


def _scenario(window, folder: Path) -> str:  # noqa: ANN001
    """Прогнать сравнение и профиль через страницу; вернуть строку-результат."""
    unknown = _write(folder / "unknown.txt", _lines(_CASUAL, 1, False))
    same = _write(folder / "same.txt", _lines(_CASUAL, 2, False))
    other = _write(folder / "other.txt", _lines(_FORMAL, 3, True))
    report = folder / "report.html"

    _wait(
        window,
        "typeof window.pywebview !== 'undefined' && !!document.getElementById('go')"
        " && document.getElementById('disclaimer').textContent.length > 0",
        PAGE_TIMEOUT,
        "загрузка страницы",
    )
    if window.evaluate_js("document.getElementById('go').disabled") is not True:
        raise AssertionError("кнопка «Сравнить» доступна до выбора файлов")

    def source(path: str) -> str:
        return json.dumps({"spec": f"file:{path}", "label": Path(path).name})

    window.evaluate_js(
        f"(state.unknown = {source(unknown)},"
        f" state.candidates.push({source(same)}, {source(other)}),"
        " refreshCompare(), document.getElementById('save-report').click(),"
        f" document.getElementById('report').value = {json.dumps(str(report))},"
        " document.getElementById('go').click(), true)"
    )
    _wait(
        window,
        "document.querySelectorAll('.cand').length === 2",
        JOB_TIMEOUT,
        "результат сравнения",
    )
    names = window.evaluate_js(
        "[...document.querySelectorAll('.cand .name')].map(n => n.textContent)"
    )
    if names != ["same.txt", "other.txt"]:
        raise AssertionError(f"сравнение: порядок кандидатов {names}")
    if not window.evaluate_js("document.querySelector('.cand.top .why mark') !== null"):
        raise AssertionError("в окне нет слов, сближающих автора")
    if not window.evaluate_js("document.getElementById('error').hidden"):
        raise AssertionError(
            "в окне показана ошибка: "
            + str(window.evaluate_js("document.getElementById('error').textContent"))
        )
    if not report.exists() or "Отчёт chatstyle" not in report.read_text(encoding="utf-8"):
        raise AssertionError("отчёт не создан")

    window.evaluate_js(
        f"(state.profile = {source(same)}, refreshCompare(),"
        " document.getElementById('tab-profile').click(),"
        " document.getElementById('go-profile').click(), true)"
    )
    _wait(
        window, "document.querySelectorAll('.feature').length === 15", JOB_TIMEOUT, "профиль стиля"
    )
    return "OK: сравнение 2 кандидатов, отчёт, профиль"


def check() -> str:
    """Выполнить проверки и вернуть строку-результат; исключение означает провал."""
    import webview

    from chatstyle.gui.app import create_window

    outcome: dict[str, object] = {}

    def work(window) -> None:  # noqa: ANN001
        try:
            with tempfile.TemporaryDirectory() as tmp:
                outcome["message"] = _scenario(window, Path(tmp))
        except BaseException as exc:  # noqa: BLE001 - любая ошибка должна попасть в результат
            outcome["error"] = "".join(traceback.format_exception(exc))
        finally:
            window.destroy()

    window = create_window(hidden=True)
    watchdog = threading.Timer(PAGE_TIMEOUT + 2 * JOB_TIMEOUT, window.destroy)
    watchdog.daemon = True
    watchdog.start()
    try:
        webview.start(work, window, gui="edgechromium")
    finally:
        watchdog.cancel()
    if "error" in outcome:
        raise AssertionError(str(outcome["error"]))
    if "message" not in outcome:
        raise AssertionError("самопроверка не завершилась")
    return str(outcome["message"])


def run(result_path: Path) -> int:
    """Записать результат самопроверки в файл; код выхода 0 при успехе."""
    try:
        message, code = check(), 0
    except Exception:  # noqa: BLE001 - любая ошибка должна попасть в файл результата
        message, code = "FAIL:\n" + traceback.format_exc(), 1
    result_path.write_text(message + "\n", encoding="utf-8")
    return code
