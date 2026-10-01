from pathlib import Path

from chatstyle.collectors.tg_export import read_tg_export
from chatstyle.collectors.txt import read_txt
from chatstyle.errors import ChatstyleError

__all__ = ["collect", "split_spec"]


def split_spec(spec: str) -> tuple[str, str]:
    """Разделить спецификацию источника по первому двоеточию."""
    scheme, sep, value = spec.partition(":")
    if not sep or not scheme or not value:
        raise ChatstyleError(
            f"Некорректный источник «{spec}». "
            "Укажите его в виде схема:значение, например file:chat.txt"
        )
    return scheme.lower(), value


def collect(spec: str) -> list[str]:
    """Собрать сообщения из источника, заданного спецификацией."""
    scheme, value = split_spec(spec)

    if scheme == "file":
        return read_txt(Path(value))

    if scheme == "tgexport":
        path_part, sep, sender = value.rpartition("#")
        if not sep or not path_part or not sender.strip():
            raise ChatstyleError(
                "Для tgexport укажите путь и имя отправителя: "
                "tgexport:путь/result.json#Имя Отправителя"
            )
        return read_tg_export(Path(path_part), sender.strip())

    if scheme == "tg":
        raise ChatstyleError(f"Источник {scheme}: пока не реализован.")

    raise ChatstyleError(f"Неизвестный тип источника «{scheme}». Доступно: file, tg, tgexport.")
