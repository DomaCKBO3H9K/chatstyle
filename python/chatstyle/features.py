"""Стилевые признаки автора: тонкая обёртка над ядром со словарями из ресурсов."""

from collections.abc import Sequence

from chatstyle import _core
from chatstyle.errors import ChatstyleError
from chatstyle.lexicon import conjunctions, filler_words, function_words, nonstandard_words
from chatstyle.preprocess import MENTION_TOKEN, URL_TOKEN

FUNCTION_WORD_PREFIX = "fw:"
FILLER_WORD_PREFIX = "fl:"
NONSTANDARD_WORD_PREFIX = "ms:"

# Группы дополнительных признаков ядра (маска kGroup* в style_features.hpp). Базовые признаки
# (скобки, многоточия, «ё», латиница, эмодзи, длина сообщения, слова-словари) считаются всегда.
STYLE_GROUP_BITS: dict[str, int] = {
    "punctuation": 1,
    "orthography": 2,
    "words": 4,
    "sentences": 8,
}
ALL_STYLE_GROUPS: tuple[str, ...] = tuple(STYLE_GROUP_BITS)

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
    "p:comma_per_word": "запятых на слово",
    "p:comma_before_conj": "доля союзов, перед которыми стоит запятая",
    "p:no_space_after_comma": "доля запятых без пробела после",
    "p:space_before_punct": "доля знаков «, . ! ?» с пробелом перед ними",
    "p:dash": "тире на сообщение",
    "p:guillemets": "доля «ёлочек» среди кавычек",
    "p:end_none": "доля сообщений без знака в конце",
    "f:capital_start": "доля сообщений с заглавной буквы",
    "f:caps_words": "слов КАПСОМ на сообщение",
    "f:capital_after_dot": "доля заглавных букв после точки внутри сообщения",
    "f:yo_ratio": "доля «ё» среди «е» и «ё»",
    "f:latin_share": "доля латинских букв",
    "f:emoji": "эмодзи на сообщение",
    "o:repeat_letters": "растянутых слов («приветтт») на сообщение",
    "o:tsya_share": "доля «тся» среди «тся» и «ться»",
    "o:mixed_script": "доля слов со смесью кириллицы и латиницы",
    "o:double_space": "двойных пробелов на сообщение",
    "o:nonstandard": "доля слов из списка нестандартных написаний",
    "w:mattr": "разнообразие слов (скользящее окно из 50 слов)",
    "w:avg_word_len": "средняя длина слова, букв",
    "w:long_words": "доля длинных слов (9 букв и больше)",
    "w:short_words": "доля коротких слов (до 2 букв)",
    "s:avg_sentence_words": "средняя длина предложения, слов",
    "s:per_message": "предложений на сообщение",
    "s:short_share": "доля коротких предложений (до 3 слов)",
    "s:long_share": "доля длинных предложений (15 слов и больше)",
    "s:multi_share": "доля сообщений из нескольких предложений",
    "r:avg_chars": "средняя длина сообщения, символов",
    "r:avg_words": "средняя длина сообщения, слов",
}

# Разделы профиля: по первой букве ключа признака
FEATURE_SECTIONS: dict[str, str] = {
    "punctuation": "Пунктуация",
    "writing": "Регистр и орфография",
    "words": "Слова",
    "sentences": "Предложения",
    "message": "Сообщения",
}
_SECTION_BY_PREFIX = {
    "p": "punctuation",
    "f": "writing",
    "o": "writing",
    "w": "words",
    "s": "sentences",
    "r": "message",
}


def feature_section(key: str) -> str:
    """Раздел профиля для ключа признака (`p:comma_per_word` -> `punctuation`)."""
    return _SECTION_BY_PREFIX[key.partition(":")[0]]


def style_groups_mask(groups: Sequence[str]) -> int:
    """Маска групп ядра по именам; неизвестное имя — ошибка с перечнем допустимых."""
    mask = 0
    for name in groups:
        if name not in STYLE_GROUP_BITS:
            allowed = ", ".join(ALL_STYLE_GROUPS)
            raise ChatstyleError(f"Неизвестная группа признаков «{name}». Допустимые: {allowed}.")
        mask |= STYLE_GROUP_BITS[name]
    return mask


def parse_style_groups(text: str) -> tuple[str, ...]:
    """Группы из строки командной строки: `all`, `none` или список через запятую."""
    value = text.strip().lower()
    if value in ("", "all"):
        return ALL_STYLE_GROUPS
    if value == "none":
        return ()
    names = tuple(part.strip() for part in value.split(",") if part.strip())
    style_groups_mask(names)  # проверка имён
    return tuple(name for name in ALL_STYLE_GROUPS if name in names)


def style_features(
    messages: Sequence[str], groups: Sequence[str] = ALL_STYLE_GROUPS
) -> dict[str, float]:
    """Стилевые признаки (кроме n-грамм) по предобработанным сообщениям автора.

    Ключи отсортированы; набор ключей полный для выбранных групп, нулевые значения тоже
    присутствуют.
    """
    return _core.style_features(
        list(messages),
        function_words(),
        filler_words(),
        [URL_TOKEN, MENTION_TOKEN],
        nonstandard_words(),
        conjunctions(),
        style_groups_mask(groups),
    )


def describe_feature(key: str) -> str:
    """Читаемое название признака ядра для отчётов: `fw:и` -> «служебное слово «и»»."""
    if key in FEATURE_LABELS:
        return FEATURE_LABELS[key]
    if key.startswith(FUNCTION_WORD_PREFIX):
        return f"служебное слово «{key[len(FUNCTION_WORD_PREFIX) :]}»"
    if key.startswith(FILLER_WORD_PREFIX):
        return f"слово-паразит «{key[len(FILLER_WORD_PREFIX) :]}»"
    if key.startswith(NONSTANDARD_WORD_PREFIX):
        return f"нестандартное написание «{key[len(NONSTANDARD_WORD_PREFIX) :]}»"
    return key


WORD_LIST_TITLES: tuple[tuple[str, str], ...] = (
    (FUNCTION_WORD_PREFIX, "Частые служебные слова"),
    (FILLER_WORD_PREFIX, "Частые слова-паразиты"),
    (NONSTANDARD_WORD_PREFIX, "Частые нестандартные написания"),
)


def top_words(features: dict[str, float], prefix: str, limit: int) -> list[tuple[str, float]]:
    """Самые частые слова словаря с данным префиксом (`fw:` или `fl:`): (слово, частота).

    Слова с нулевой частотой не включаются; при равенстве порядок по алфавиту.
    """
    ranked = [
        (key[len(prefix) :], value)
        for key, value in features.items()
        if key.startswith(prefix) and value > 0
    ]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked[:limit]


def word_list_lines(features: dict[str, float], limit: int) -> list[str]:
    """Строки «Частые служебные слова: и 0.051, там 0.038» для вывода профиля."""
    lines = []
    for prefix, title in WORD_LIST_TITLES:
        ranked = top_words(features, prefix, limit)
        text = ", ".join(f"{word} {value:.3f}" for word, value in ranked) or "нет"
        lines.append(f"{title}: {text}")
    return lines
