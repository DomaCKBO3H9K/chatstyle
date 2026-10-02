"""Модуль преобразования сообщений в эмодзи-кластеры для подсчёта сходства.

Превращает эмодзи-кластеры в одиночные символы, чтобы существующее ядро
(символьные n-граммы 1–4) могло считать сходство по эмодзи.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

# Регулярное выражение для одного эмодзи-кластера
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff☀-➿⬀-⯿⌀-⏿][\ufe0f\U0001f3fb-\U0001f3ff]*"
    "(?:\u200d[\U0001f000-\U0001faff☀-➿⬀-⯿⌀-⏿][\ufe0f\U0001f3fb-\U0001f3ff]*)*"
)


def emoji_of(message: str) -> list[str]:
    """Возвращает все эмодзи-кластеры сообщения по порядку."""
    return _EMOJI.findall(message)


def emoji_views(
    unknown: Sequence[str],
    candidates: Mapping[str, Sequence[str]],
) -> tuple[list[str], dict[str, list[str]]]:
    """Преобразует сообщения в строки из символов эмодзи-кластеров.

    1) Собирает для каждого автора (неизвестный и каждый кандидат) множество его эмодзи-кластеров.
    2) Каждый уникальный кластер (по всем авторам) сортируется и получает символ
       ``chr(0xF0000 + i)``, где ``i`` — номер кластера в отсортированном списке.
       Если кластеров больше 60000, лишние игнорируются.
    3) Для каждого сообщения возвращает строку из кодов его эмодзи по порядку.
       Сообщения без эмодзи пропускаются.

    :param unknown: сообщения неизвестного автора.
    :param candidates: сообщения кандидатов в виде словаря {имя_автора: сообщения}.
    :return: кортеж (результат для неизвестного, результат для кандидатов).
    """
    # 1) Собрать множество эмодзи-кластеров для каждого автора
    author_emoji: dict[str, set[str]] = {}
    author_emoji["__unknown__"] = set()
    for msg in unknown:
        author_emoji["__unknown__"].update(emoji_of(msg))
    for author, msgs in candidates.items():
        author_emoji[author] = set()
        for msg in msgs:
            author_emoji[author].update(emoji_of(msg))

    # 2) Отобрать все уникальные кластеры и отсортировать их
    all_emoji = sorted(emoji for emoji_set in author_emoji.values() for emoji in emoji_set)

    # 3) Назначить символы кластерам
    emoji_to_code: dict[str, str] = {}
    for i, emoji in enumerate(all_emoji):
        if i < 60000:
            emoji_to_code[emoji] = chr(0xF0000 + i)

    # 4) Преобразовать сообщения в строки из символов
    def encode_messages(messages: Sequence[str]) -> list[str]:
        result: list[str] = []
        for msg in messages:
            codes = [emoji_to_code.get(emoji, chr(0xF0000)) for emoji in emoji_of(msg)]
            if codes:
                result.append("".join(codes))
        return result

    unknown_result = encode_messages(unknown)
    candidates_result = {author: encode_messages(msgs) for author, msgs in candidates.items()}

    return unknown_result, candidates_result
