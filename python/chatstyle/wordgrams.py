"""Модуль преобразования слов в символы для подсчёта словных n-грамм.

Превращает слова в одиночные символы, чтобы существующее ядро
(символьные n-граммы 1–4) могло считать словные n-граммы 1–4.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

# Регулярное выражение для «слова»: буквы Unicode, допускаются дефисы внутри
_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)

# Символ для слова, которое есть только у одного автора
RARE_CODE = chr(0xF0000)

# Область личного использования Unicode для кодов общих слов
FIRST_CODE = 0xF0001
LAST_CODE = 0xFFFFD


def words_of(message: str) -> list[str]:
    """Возвращает все слова сообщения в нижнем регистре."""
    return _WORD.findall(message.lower())


def word_views(
    unknown: Sequence[str],
    candidates: Mapping[str, Sequence[str]],
) -> tuple[list[str], dict[str, list[str]]]:
    """Преобразует сообщения в строки из символов слов.

    1) Собирает для каждого автора (неизвестный и каждый кандидат) множество его слов.
    2) Слово считается общим, если оно встречается минимум у двух авторов;
       остальные слова превращаются в :data:`RARE_CODE`.
    3) Каждому общему слову назначает символ ``chr(FIRST_CODE + i)``,
       где ``i`` — номер слова в отсортированном списке общих слов.
       Если слов больше, чем символов в диапазоне ``FIRST_CODE..LAST_CODE``,
       лишние слова (по порядку) также получают :data:`RARE_CODE`.
    4) Для каждого сообщения возвращает строку из кодов слов.
       Сообщения без слов пропускаются.

    :param unknown: сообщения неизвестного автора.
    :param candidates: сообщения кандидатов в виде словаря {имя_автора: сообщения}.
    :return: кортеж (результат для неизвестного, результат для кандидатов).
    """
    # 1) Собрать множество слов для каждого автора
    author_words: dict[str, set[str]] = {}
    author_words["__unknown__"] = set()
    for msg in unknown:
        author_words["__unknown__"].update(words_of(msg))
    for author, msgs in candidates.items():
        author_words[author] = set()
        for msg in msgs:
            author_words[author].update(words_of(msg))

    # 2) Подсчитать, у скольких авторов каждое слово встречается
    word_author_count: dict[str, int] = {}
    for words in author_words.values():
        for word in words:
            word_author_count[word] = word_author_count.get(word, 0) + 1

    # 3) Отобрать общие слова и отсортировать их
    common_words = sorted(word for word, count in word_author_count.items() if count >= 2)

    # 4) Назначить символы общим словам
    word_to_code: dict[str, str] = {}
    available_codes = LAST_CODE - FIRST_CODE + 1
    for i, word in enumerate(common_words):
        if i < available_codes:
            word_to_code[word] = chr(FIRST_CODE + i)
        else:
            word_to_code[word] = RARE_CODE

    # 5) Преобразовать сообщения в строки из символов
    def encode_messages(messages: Sequence[str]) -> list[str]:
        result: list[str] = []
        for msg in messages:
            codes = [word_to_code.get(word, RARE_CODE) for word in words_of(msg)]
            if codes:
                result.append("".join(codes))
        return result

    unknown_result = encode_messages(unknown)
    candidates_result = {author: encode_messages(msgs) for author, msgs in candidates.items()}

    return unknown_result, candidates_result
