from pathlib import Path

import pytest
from chatstyle.collectors.tg_export import read_tg_export
from chatstyle.errors import ChatstyleError

FIXTURES = Path(__file__).parent / "fixtures"
EXPORT = FIXTURES / "result.json"

ANNA = [
    "привет))",
    "смотри https://example.com/a круто",
    "ну реально норм, @boris_k глянь",
    "короче вот фотка",
    "ладно))\nщас дойду",
]

BORIS = [
    "Привет. Как дела?",
    "Посмотрю вечером.",
    "ок",
]


def test_sender_by_name() -> None:
    """По имени автора (полное ФИО) получаем только его сообщения."""
    result = read_tg_export(EXPORT, "Анна Петрова")
    assert result == ANNA


def test_other_sender() -> None:
    """По имени другого автора получаем его сообщения."""
    result = read_tg_export(EXPORT, "Борис")
    assert result == BORIS


def test_sender_by_from_id() -> None:
    """По полному from_id получаем сообщения."""
    assert read_tg_export(EXPORT, "user111") == ANNA
    assert read_tg_export(EXPORT, "user222") == BORIS


def test_sender_by_numeric_id() -> None:
    """По числовому id (без префикса) получаем сообщения."""
    assert read_tg_export(EXPORT, "111") == ANNA


def test_unknown_sender_lists_names() -> None:
    """Неизвестный отправитель вызывает ошибку с подсказкой доступных имён."""
    with pytest.raises(ChatstyleError) as excinfo:
        read_tg_export(EXPORT, "Вася")
    msg = str(excinfo.value)
    assert "Вася" in msg
    assert "Анна Петрова" in msg
    assert "Борис" in msg
