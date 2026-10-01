from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from chatstyle.collectors.telegram import DEFAULT_LIMIT, read_telegram
from chatstyle.collectors.tg_export import read_tg_export
from chatstyle.collectors.txt import read_txt
from chatstyle.errors import ChatstyleError

__all__ = ["CollectOptions", "collect", "split_spec"]


@dataclass(frozen=True)
class CollectOptions:
    """Параметры сбора, общие для всех источников; сейчас их использует только tg:."""

    limit: int = DEFAULT_LIMIT
    refresh: bool = False
    notify: Callable[[str], None] | None = None


def split_spec(spec: str) -> tuple[str, str]:
    """Разделить спецификацию источника по первому двоеточию."""
    scheme, sep, value = spec.partition(":")
    if not sep or not scheme or not value:
        raise ChatstyleError(
            f"Некорректный источник «{spec}». "
            "Укажите его в виде схема:значение, например file:chat.txt"
        )
    return scheme.lower(), value


def collect(spec: str, options: CollectOptions | None = None) -> list[str]:
    """Собрать сообщения из источника, заданного спецификацией."""
    opts = options if options is not None else CollectOptions()
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
        return read_telegram(value, limit=opts.limit, refresh=opts.refresh, notify=opts.notify)

    raise ChatstyleError(f"Неизвестный тип источника «{scheme}». Доступно: file, tg, tgexport.")
