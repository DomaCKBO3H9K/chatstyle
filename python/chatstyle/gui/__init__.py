"""Графический интерфейс chatstyle: окно на pywebview, вид в `gui/web`, мосты в `gui.api`."""


def main() -> int:
    """Открыть окно приложения и работать до его закрытия."""
    from chatstyle.gui.app import run

    return run()
