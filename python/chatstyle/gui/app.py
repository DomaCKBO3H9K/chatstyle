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


def index_url() -> str:
    """Адрес страницы как file://: для обычного пути pywebview поднимает локальный HTTP-сервер,
    а открытый порт на 127.0.0.1 окну не нужен и расширял бы поверхность атаки."""
    return index_path().as_uri()


_GUARDS: list[object] = []  # делегаты .NET не должны собираться сборщиком мусора


def install_navigation_guard(window) -> None:  # noqa: ANN001
    """Запретить окну любые переходы за пределы страницы интерфейса (только Windows, WebView2).

    pywebview подставляет `window.pywebview.api` в любую загруженную страницу, поэтому уход на
    чужой адрес дал бы ей доступ к методам программы. Защита ставится событием WebView2
    NavigationStarting; при любой неудаче установки вызывающий закрывает окно (отказ закрытым).
    """
    from System import Func, Type  # type: ignore[import-not-found]

    prefix = index_url().rsplit("/", 1)[0] + "/"

    def guard(sender, args) -> None:  # noqa: ANN001
        if not str(args.Uri).startswith(prefix):
            args.Cancel = True

    def on_ui_thread() -> None:
        window.native.webview.CoreWebView2.NavigationStarting += guard

    _GUARDS.append(guard)
    window.native.webview.Invoke(Func[Type](on_ui_thread))


def _report_problem(text: str) -> None:
    """Сообщить об ошибке запуска: у сборки без консоли stderr никто не увидит."""
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10)
    else:
        print(text, file=sys.stderr)


def create_window(*, hidden: bool = False):  # noqa: ANN201 - тип окна задаёт pywebview
    """Окно с подключённым Api; hidden=True нужен самопроверке (окно не показывается)."""
    import webview

    # внешние ссылки не открываются ни в окне, ни в браузере: любой переход блокируется защитой
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    holder: list[object] = []
    api = Api(lambda: holder[0] if holder else None)
    window = webview.create_window(
        TITLE,
        url=index_url(),
        js_api=api,
        width=SIZE[0],
        height=SIZE[1],
        min_size=MIN_SIZE,
        background_color=BACKGROUND,
        hidden=hidden,
    )
    holder.append(window)
    window._chatstyle_api = api  # для самопроверки: доступ к списку разрешённых путей
    if sys.platform == "win32":
        window.events.loaded += lambda: _guard_once(window)
    return window


def _guard_once(window) -> None:  # noqa: ANN001
    """Поставить защиту навигации при первой загрузке; не вышло — окно закрывается."""
    if getattr(window, "_navigation_guard", False):
        return
    window._navigation_guard = True
    try:
        install_navigation_guard(window)
    except Exception as exc:  # noqa: BLE001 - без защиты работать нельзя
        _report_problem(f"Не удалось включить защиту окна: {type(exc).__name__}: {exc}")
        window.destroy()


def run() -> int:
    """Точка входа: окно приложения до закрытия."""
    import webview

    window = create_window()
    api = window._chatstyle_api
    try:
        # приватный режим: профиль WebView2 временный, браузерное хранилище ничего не запоминает
        webview.start(gui="edgechromium" if sys.platform == "win32" else None, private_mode=True)
    except Exception as exc:  # noqa: BLE001 - любой отказ движка окна объясняем пользователю
        _report_problem(WEBVIEW2_HELP + f"{type(exc).__name__}: {exc}")
        return 1
    finally:
        api.shutdown()  # вход прерывается; в режиме «только память» сессия завершается
    return 0
