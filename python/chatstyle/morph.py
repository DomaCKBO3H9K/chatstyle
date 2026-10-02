"""Модуль разметки частей речи.

Использует pymorphy3 (необязательно). При отсутствии библиотеки
поднимает :class:`chatstyle.errors.ChatstyleError` с подсказкой
о необходимости установить дополнение ``chatstyle[morph]``.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Sequence

from .errors import CodedError
from .preprocess import MENTION_TOKEN, URL_TOKEN

# --------------------------------------------------------------------------- #
# Константы кодов частей речи
# --------------------------------------------------------------------------- #

POS_CODES: dict[str, str] = {
    "NOUN": "n",  # существительное
    "VERB": "v",  # глагол
    "INFN": "i",  # инфинитив
    "ADJF": "a",  # полное прилагательное
    "ADJS": "j",  # краткое прилагательное
    "COMP": "c",  # компаратив
    "PRTF": "t",  # полное причастие
    "PRTS": "s",  # краткое причастие
    "GRND": "g",  # деепричастие
    "NUMR": "m",  # числительное
    "ADVB": "d",  # наречие
    "NPRO": "p",  # местоимение-существительное
    "PRED": "e",  # предикатив
    "PREP": "r",  # предлог
    "CONJ": "k",  # союз
    "PRCL": "q",  # частица
    "INTJ": "h",  # междометие
}
UNKNOWN_POS_CODE = "u"  # слово известно, но POS не определён
OOV_CODE = "x"  # слово отсутствует в словаре
LATIN_CODE = "l"  # слово состоит только из латинских букв

# отсортированный кортеж всех кодов (20 штук)
ALL_CODES: tuple[str, ...] = tuple(
    sorted(set(POS_CODES.values()) | {UNKNOWN_POS_CODE, OOV_CODE, LATIN_CODE})
)

# Подсказка для пользователя, если pymorphy3 не установлен
HINT = "Части речи требуют необязательного дополнения: pip install chatstyle[morph] (pymorphy3)"

# Регулярное выражение для «слова»: буквы Unicode, допускаются дефисы внутри
_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)

# --------------------------------------------------------------------------- #
# Вспомогательные функции
# --------------------------------------------------------------------------- #


@functools.cache
def available() -> bool:
    """Возвращает ``True``, если pymorphy3 импортирован и можно создать анализатор."""
    try:
        import pymorphy3  # noqa: F401

        _ = pymorphy3.MorphAnalyzer()
        return True
    except Exception:  # pragma: no cover
        return False


def reset_cache() -> None:
    """Сбрасывает все кэши, используемые в модуле."""
    available.cache_clear()
    _analyzer.cache_clear()
    _code_of_word.cache_clear()


def require() -> None:
    """Поднимает :class:`ChatstyleError`, если библиотека недоступна."""
    if not available():
        raise CodedError("morph_missing", HINT)


@functools.cache
def _analyzer():
    """Создаёт и кэширует :class:`pymorphy3.MorphAnalyzer`."""
    import pymorphy3

    return pymorphy3.MorphAnalyzer()


@functools.lru_cache(maxsize=200_000)
def _code_of_word(word: str) -> str:
    """Возвращает однобуквенный код части речи для одного слова."""
    lowered = word.lower()
    # латиница (с дефисами) → LATIN_CODE
    if re.fullmatch(r"[a-z]+(?:-[a-z]+)*", lowered):
        return LATIN_CODE

    analyzer = _analyzer()
    parses = analyzer.parse(lowered)
    if not parses:
        return OOV_CODE
    best = parses[0]
    if not best.is_known:
        return OOV_CODE
    return POS_CODES.get(best.tag.POS, UNKNOWN_POS_CODE)


def word_codes(message: str) -> list[str]:
    """Список кодов частей речи для всех слов в сообщении.

    Служебные токены ``<URL>`` и ``<MENTION>`` заменяются пробелом.
    """
    require()
    cleaned = message.replace(URL_TOKEN, " ").replace(MENTION_TOKEN, " ")
    words = _WORD.findall(cleaned)
    return [_code_of_word(w) for w in words]


def tag_message(message: str) -> str:
    """Коды частей речи, разделённые пробелом."""
    return " ".join(word_codes(message))


def pos_view(messages: Sequence[str]) -> list[str]:
    """Список строк‑тегов (коды через пробел) для непустых сообщений."""
    result: list[str] = []
    for msg in messages:
        codes = word_codes(msg)
        if codes:
            result.append(" ".join(codes))
    return result


def compact_view(messages: Sequence[str]) -> list[str]:
    """Список строк‑тегов без пробелов для непустых сообщений."""
    result: list[str] = []
    for msg in messages:
        codes = word_codes(msg)
        if codes:
            result.append("".join(codes))
    return result
