"""Словари служебных слов и слов-паразитов (ресурсы пакета)."""

import unicodedata
from functools import cache
from importlib import resources

FUNCTION_WORDS_FILE = "function_words_ru.txt"
FILLER_WORDS_FILE = "filler_words_ru.txt"
NONSTANDARD_WORDS_FILE = "nonstandard_ru.txt"
CONJUNCTIONS_FILE = "conjunctions_ru.txt"


def parse_word_list(text: str) -> list[str]:
    """Разобрать список слов: пропустить пустые строки и комментарии, убрать дубли.

    Слова приводятся к NFC и нижнему регистру. Запись с пробелами (несколько слов) —
    ошибка словаря, а не данных пользователя, поэтому поднимается ValueError.
    """
    words: list[str] = []
    seen: set[str] = set()
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        word = unicodedata.normalize("NFC", line).lower()
        if any(char.isspace() for char in word):
            raise ValueError(f"Строка {number}: в словаре допускаются только однословные записи")
        if word not in seen:
            seen.add(word)
            words.append(word)
    return words


@cache
def _load(name: str) -> tuple[str, ...]:
    text = resources.files("chatstyle").joinpath("resources", name).read_text(encoding="utf-8")
    return tuple(parse_word_list(text))


def function_words() -> list[str]:
    """Служебные слова: предлоги, союзы, частицы, местоимения."""
    return list(_load(FUNCTION_WORDS_FILE))


def filler_words() -> list[str]:
    """Слова-паразиты и разговорные вставки."""
    return list(_load(FILLER_WORDS_FILE))


def nonstandard_words() -> list[str]:
    """Нестандартные написания и сленг: признаки o:nonstandard и ms:<слово>."""
    return list(_load(NONSTANDARD_WORDS_FILE))


def conjunctions() -> list[str]:
    """Союзы, перед которыми по правилам ставится запятая: признак p:comma_before_conj."""
    return list(_load(CONJUNCTIONS_FILE))
