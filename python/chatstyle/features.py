"""Стилевые признаки автора: тонкая обёртка над ядром со словарями из ресурсов."""

from collections.abc import Sequence

from chatstyle import _core
from chatstyle.lexicon import filler_words, function_words
from chatstyle.preprocess import MENTION_TOKEN, URL_TOKEN

FUNCTION_WORD_PREFIX = "fw:"
FILLER_WORD_PREFIX = "fl:"

FEATURE_LABELS: dict[str, str] = {
    "p:paren1": "«)» на сообщение",
    "p:paren2": "«))» на сообщение",
    "p:paren3+": "«)))» и длиннее, на сообщение",
    "p:ellipsis": "многоточие на сообщение",
    "p:excl1": "«!» на сообщение",
    "p:excl2+": "«!!» и длиннее, на сообщение",
    "p:quest1": "«?» на сообщение",
    "p:quest2+": "«??» и длиннее, на сообщение",
    "p:end_dot": "доля сообщений с точкой в конце",
    "f:capital_start": "доля сообщений с заглавной буквы",
    "f:yo_ratio": "доля «ё» среди «е» и «ё»",
    "f:latin_share": "доля латинских букв",
    "f:emoji": "эмодзи на сообщение",
    "r:avg_chars": "средняя длина сообщения, символов",
    "r:avg_words": "средняя длина сообщения, слов",
}


def style_features(messages: Sequence[str]) -> dict[str, float]:
    """Стилевые признаки (кроме n-грамм) по предобработанным сообщениям автора.

    Ключи отсортированы; набор ключей полный, нулевые значения тоже присутствуют.
    """
    return _core.style_features(
        list(messages),
        function_words(),
        filler_words(),
        [URL_TOKEN, MENTION_TOKEN],
    )


def describe_feature(key: str) -> str:
    """Читаемое название признака ядра для отчётов: `fw:и` -> «служебное слово «и»»."""
    if key in FEATURE_LABELS:
        return FEATURE_LABELS[key]
    if key.startswith(FUNCTION_WORD_PREFIX):
        return f"служебное слово «{key[len(FUNCTION_WORD_PREFIX) :]}»"
    if key.startswith(FILLER_WORD_PREFIX):
        return f"слово-паразит «{key[len(FILLER_WORD_PREFIX) :]}»"
    return key
