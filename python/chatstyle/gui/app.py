"""Окно приложения: pywebview показывает страницу из `chatstyle/gui/web`, Python отвечает через Api.

Вид целиком в HTML/CSS/JS, расчёты и данные для показа готовят `chatstyle.gui.api` и
`chatstyle.gui.model`. Страница грузится из файлов пакета, наружу в сеть окно не ходит.
"""

import ctypes
import sys
from importlib import resources
from pathlib import Path

from chatstyle.gui.api import Api

TITLE = "chatstyle"
SIZE = (1180, 820)
MIN_SIZE = (900, 640)
BACKGROUND = "#F1F3F7"
WEBVIEW2_HELP = (
    "Для окна нужен Microsoft Edge WebView2 Runtime. Скачайте его на странице "
    "https://developer.microsoft.com/microsoft-edge/webview2/ (Evergreen Bootstrapper) "
    "и запустите приложение снова.\n\nПодробности: "
)


def index_path() -> Path:
    """Страница интерфейса внутри пакета (рядом лежат style.css и app.js)."""
    return Path(str(resources.files("chatstyle").joinpath("gui", "web", "index.html")))


def _report_problem(text: str) -> None:
    """Сообщить об ошибке запуска: у сборки без консоли stderr никто не увидит."""
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10)
    else:
        print(text, file=sys.stderr)


def create_window(*, hidden: bool = False):  # noqa: ANN201 - тип окна задаёт pywebview
    """Окно с подключённым Api; hidden=True нужен самопроверке (окно не показывается)."""
    import webview

    holder: list[object] = []
    api = Api(lambda: holder[0] if holder else None)
    window = webview.create_window(
        TITLE,
        url=str(index_path()),
        js_api=api,
        width=SIZE[0],
        height=SIZE[1],
        min_size=MIN_SIZE,
        background_color=BACKGROUND,
        hidden=hidden,
    )
    holder.append(window)
    return window


def run() -> int:
    """Точка входа: окно приложения до закрытия."""
    import webview

    create_window()
    try:
        webview.start(gui="edgechromium" if sys.platform == "win32" else None)
    except Exception as exc:  # noqa: BLE001 - любой отказ движка окна объясняем пользователю
        _report_problem(WEBVIEW2_HELP + f"{type(exc).__name__}: {exc}")
        return 1
    return 0
