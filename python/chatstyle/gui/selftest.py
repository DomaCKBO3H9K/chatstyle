"""Самопроверка окна без участия пользователя: `chatstyle-gui.exe --selftest ФАЙЛ`.

Окно создаётся скрытым и работает как настоящее: страница `gui/web` загружается в WebView2, форма
заполняется состоянием страницы, кнопки нажимаются внутри страницы (DOM), расчёт проходит весь
путь JavaScript -> Api -> ядро -> JavaScript. Ничего не отправляется ни в окна других программ,
ни на рабочий стол. Результат (`OK ...` или текст ошибки) записывается в ФАЙЛ: у сборки без
консоли нет stdout. Нужна, чтобы проверить собранный exe (WebView2, ресурсы, потоки, ядро)
без ручных кликов.
"""

import json
import os
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


def _listening_sockets() -> list[str]:
    """Слушающие TCP-порты процесса и его потомков (Windows); у окна их быть не должно."""
    import subprocess
    import sys

    from chatstyle.securestore import system_tool

    if sys.platform != "win32":
        return []
    script = (
        "$ids = @(" + str(os.getpid()) + "); $n = 1;"
        " while ($n -gt 0) { $new = Get-CimInstance Win32_Process |"
        " Where-Object { $ids -contains $_.ParentProcessId -and $ids -notcontains $_.ProcessId } |"
        " ForEach-Object { $_.ProcessId }; $n = @($new).Count; $ids += $new };"
        " $ids -join ','"
    )
    flags = subprocess.CREATE_NO_WINDOW
    ids = subprocess.run(
        [
            system_tool("WindowsPowerShell", "v1.0", "powershell.exe"),
            "-NoProfile",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=flags,
    ).stdout.strip()
    pids = {item for item in ids.split(",") if item}
    net = subprocess.run(
        [system_tool("netstat.exe"), "-ano", "-p", "TCP"],
        capture_output=True,
        text=True,
        creationflags=flags,
    ).stdout
    return [
        line.strip()
        for line in net.splitlines()
        if "LISTENING" in line and line.split()[-1] in pids
    ]


def _check_vault(folder: Path) -> None:
    """Хранилище секретов работает в этой сборке: пароль (scrypt + AES-GCM) и DPAPI."""
    from chatstyle.securestore import (
        MODE_DPAPI,
        MODE_PASSWORD,
        Vault,
        VaultError,
        dpapi_available,
    )

    secret = "секрет-для-самопроверки"
    modes = [(MODE_PASSWORD, "самопроверка пароль 1")]
    if dpapi_available():
        modes.append((MODE_DPAPI, None))
    for mode, password in modes:
        vault = Vault(folder / f"vault-{mode}.json", backoff=False)
        vault.create(mode, password)
        vault.set("k", secret)
        vault.lock()
        if mode == MODE_PASSWORD:
            try:
                vault.unlock("неверный пароль 12345")
            except VaultError as exc:
                if exc.code != "wrong_password":
                    raise
            else:
                raise AssertionError("хранилище открылось неверным паролем")
        vault.unlock(password)
        if vault.get("k") != secret:
            raise AssertionError(f"хранилище {mode}: значение не вернулось")
        if secret in vault.path.read_text(encoding="utf-8"):
            raise AssertionError(f"хранилище {mode}: секрет лежит на диске открытым текстом")


def _check_morph() -> None:
    """Части речи (если дополнение в сборке есть): разметка и профиль работают."""
    from chatstyle import morph

    if not morph.available():
        return
    if morph.word_codes("мама иду ваще hello") != ["n", "v", "x", "l"]:
        raise AssertionError("разметка частей речи вернула неожиданные коды")


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
    _check_vault(folder)
    _check_morph()
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

    # в настоящем окне пути выбираются в диалогах; здесь их «выбирает» самопроверка
    api = window._chatstyle_api
    for path in (unknown, same, other):
        api._remember_path(path)
    api._remember_report(str(report))

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
    from chatstyle.features import FEATURE_LABELS

    _wait(
        window,
        f"document.querySelectorAll('.feature').length >= {len(FEATURE_LABELS)}",
        JOB_TIMEOUT,
        "профиль стиля",
    )
    for code, direction, compare in (("ar", "rtl", "قارن"), ("en", "ltr", "Compare")):
        window.evaluate_js(
            f"(document.getElementById('lang').value = '{code}',"
            " document.getElementById('lang').dispatchEvent(new Event('change')), true)"
        )
        seen = window.evaluate_js(
            "[document.documentElement.dir, document.getElementById('go-text').textContent,"
            " document.querySelector('.verdict') !== null]"
        )
        if seen != [direction, compare, True]:
            raise AssertionError(
                f"язык {code}: ожидали {[direction, compare, True]}, увидели {seen}"
            )
    window.evaluate_js("document.getElementById('tg-chip').click()")
    _wait(
        window,
        "document.getElementById('tg').open === true"
        " && document.getElementById('tg-body').children.length > 0"
        " && document.getElementById('tg-chip').textContent.length > 0",
        15.0,
        "окно подключения Telegram",
    )
    window.evaluate_js("document.getElementById('tg-close').click()")
    window.evaluate_js("location.href = 'http://127.0.0.1:1/'")
    time.sleep(1.0)
    where = window.evaluate_js("location.protocol")
    if where != "file:":
        raise AssertionError(f"окно ушло со страницы интерфейса: {where}")
    listening = _listening_sockets()
    if listening:
        raise AssertionError(f"процесс окна слушает порты: {listening}")
    before = window.evaluate_js("currentTheme()")
    window.evaluate_js("document.getElementById('theme').click()")
    after = window.evaluate_js("document.documentElement.dataset.theme")
    if after == before or after not in ("light", "dark"):
        raise AssertionError(f"тема не переключилась: было {before}, стало {after}")
    return "OK: сравнение 2 кандидатов, отчёт, профиль, языки, Telegram, хранилище, тема"


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

    # самопроверка не трогает настоящие данные пользователя: своя временная папка данных
    home = tempfile.TemporaryDirectory()
    previous = os.environ.get("CHATSTYLE_HOME")
    os.environ["CHATSTYLE_HOME"] = home.name
    window = create_window(hidden=True)
    watchdog = threading.Timer(PAGE_TIMEOUT + 2 * JOB_TIMEOUT, window.destroy)
    watchdog.daemon = True
    watchdog.start()
    try:
        webview.start(work, window, gui="edgechromium")
    finally:
        watchdog.cancel()
        if previous is None:
            os.environ.pop("CHATSTYLE_HOME", None)
        else:
            os.environ["CHATSTYLE_HOME"] = previous
        home.cleanup()
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
