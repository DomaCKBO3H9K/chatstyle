"""Сообщения вместе с моментами их отправки (нужны для ритма письма).

`Messages` — обычный список строк, поэтому весь прежний код работает с ним без изменений;
необязательное поле `times` хранит момент каждого сообщения в секундах от 1970-01-01 по
ЛОКАЛЬНОМУ времени автора (часовой пояс уже учтён, чтобы час суток был «настенным»).
Источники без дат (обычный текстовый файл) отдают `times = None`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime


class Messages(list[str]):
    """Список текстов сообщений с необязательными моментами отправки."""

    times: list[int | None] | None

    def __init__(
        self, texts: Iterable[str] = (), times: Sequence[int | None] | None = None
    ) -> None:
        super().__init__(texts)
        if times is not None and len(times) != len(self):
            raise ValueError("Число моментов времени должно совпадать с числом сообщений.")
        self.times = list(times) if times is not None else None


def local_seconds(moment: datetime) -> int:
    """Секунды «настенного» локального времени: aware-момент переводится в часовой пояс системы."""
    local = moment.astimezone() if moment.tzinfo is not None else moment
    return int(local.replace(tzinfo=UTC).timestamp())


def parse_export_date(value: object) -> int | None:
    """Поле `date` экспорта Telegram Desktop («2024-01-02T10:00:00», местное время) или None."""
    if not isinstance(value, str):
        return None
    try:
        return local_seconds(datetime.fromisoformat(value))
    except ValueError:
        return None


def known_times(messages: Sequence[str]) -> list[int]:
    """Моменты сообщений, которые известны (у списка без времени — пусто)."""
    times = getattr(messages, "times", None)
    if not times:
        return []
    return [moment for moment in times if moment is not None]
